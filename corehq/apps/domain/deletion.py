import itertools
import logging
from collections import Counter
from datetime import date

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.db.models import Q

from corehq.sql_db.util import get_db_aliases_for_partitioned_query
from dimagi.utils.chunked import chunked

from corehq.apps.accounting.models import Subscription
from corehq.apps.accounting.utils import get_change_status
from corehq.apps.domain.utils import silence_during_tests
from corehq.apps.userreports.dbaccessors import (
    delete_all_ucr_tables_for_domain,
)
from corehq.blobs import CODES, get_blob_db
from corehq.blobs.models import BlobMeta
from corehq.form_processor.backends.sql.dbaccessors import doc_type_to_state
from corehq.form_processor.interfaces.dbaccessors import (
    CaseAccessors,
    FormAccessors,
)
from corehq.util.log import with_progress_bar

logger = logging.getLogger(__name__)


class BaseDeletion(object):

    def __init__(self, app_label, models):
        self.app_label = app_label
        self.models = models

    def get_model_classes(self):
        return [
            apps.get_model(self.app_label, model) for model in self.models
        ]

    def is_app_installed(self):
        try:
            return bool(apps.get_app_config(self.app_label))
        except LookupError:
            return False


class CustomDeletion(BaseDeletion):

    def __init__(self, app_label, deletion_fn, models):
        super(CustomDeletion, self).__init__(app_label, models)
        self.deletion_fn = deletion_fn

    def execute(self, domain_name):
        if self.is_app_installed():
            self.deletion_fn(domain_name)


class RawDeletion(BaseDeletion):

    def __init__(self, app_label, models, raw_query):
        super(RawDeletion, self).__init__(app_label, models)
        self.raw_query = raw_query

    def execute(self, cursor, domain_name):
        if self.is_app_installed():
            cursor.execute(self.raw_query, [domain_name])


class ModelDeletion(BaseDeletion):

    def __init__(self, app_label, model_name, domain_filter_kwarg, extra_models=None):
        models = extra_models or []
        models.append(model_name)
        super(ModelDeletion, self).__init__(app_label, models)
        self.domain_filter_kwarg = domain_filter_kwarg
        self.model_name = model_name

    def get_model_class(self):
        return apps.get_model(self.app_label, self.model_name)

    def execute(self, domain_name):
        if not domain_name:
            # The Django orm will properly turn a None domain_name to a
            # IS NULL filter. We don't want to allow deleting records for
            # NULL domain names since they might have special meaning (like
            # in some of the SMS models).
            raise RuntimeError("Expected a valid domain name")
        if self.is_app_installed():
            model = self.get_model_class()
            model.objects.filter(**{self.domain_filter_kwarg: domain_name}).delete()


class PartitionedModelDeletion(ModelDeletion):
    def execute(self, domain_name):
        if not self.is_app_installed():
            return
        model = self.get_model_class()
        for db_name in get_db_aliases_for_partitioned_query():
            model.objects.using(db_name).filter(**{self.domain_filter_kwarg: domain_name}).delete()


def _delete_domain_backend_mappings(domain_name):
    model = apps.get_model('sms', 'SQLMobileBackendMapping')
    model.objects.filter(is_global=False, domain=domain_name).delete()


def _delete_domain_backends(domain_name):
    model = apps.get_model('sms', 'SQLMobileBackend')
    model.objects.filter(is_global=False, domain=domain_name).delete()


def _delete_web_user_membership(domain_name):
    from corehq.apps.users.models import WebUser
    active_web_users = WebUser.by_domain(domain_name)
    inactive_web_users = WebUser.by_domain(domain_name, is_active=False)
    for web_user in list(active_web_users) + list(inactive_web_users):
        web_user.delete_domain_membership(domain_name)
        if settings.UNIT_TESTING and not web_user.domain_memberships:
            web_user.delete(deleted_by=None)
        else:
            web_user.save()


def _terminate_subscriptions(domain_name):
    today = date.today()

    with transaction.atomic():
        current_subscription = Subscription.get_active_subscription_by_domain(domain_name)

        if current_subscription:
            current_subscription.date_end = today
            current_subscription.is_active = False
            current_subscription.save()

            current_subscription.transfer_credits()

            _, downgraded_privs, upgraded_privs = get_change_status(current_subscription.plan_version, None)
            current_subscription.subscriber.deactivate_subscription(
                downgraded_privileges=downgraded_privs,
                upgraded_privileges=upgraded_privs,
                old_subscription=current_subscription,
                new_subscription=None,
            )

        Subscription.visible_objects.filter(
            Q(date_start__gt=today) | Q(date_start=today, is_active=False),
            subscriber__domain=domain_name,
        ).update(is_hidden_to_ops=True)


def _delete_all_cases(domain_name):
    logger.info('Deleting cases...')
    case_accessor = CaseAccessors(domain_name)
    case_ids = case_accessor.get_case_ids_in_domain()
    for case_id_chunk in chunked(with_progress_bar(case_ids, stream=silence_during_tests()), 500):
        case_accessor.soft_delete_cases(list(case_id_chunk))
    logger.info('Deleting cases complete.')


def _delete_all_forms(domain_name):
    logger.info('Deleting forms...')
    form_accessor = FormAccessors(domain_name)
    form_ids = list(itertools.chain(*[
        form_accessor.get_all_form_ids_in_domain(doc_type=doc_type)
        for doc_type in doc_type_to_state
    ]))
    for form_id_chunk in chunked(with_progress_bar(form_ids, stream=silence_during_tests()), 500):
        form_accessor.soft_delete_forms(list(form_id_chunk))
    logger.info('Deleting forms complete.')



def _delete_data_files(domain_name):
    get_blob_db().bulk_delete(metas=list(BlobMeta.objects.partitioned_query(domain_name).filter(
        parent_id=domain_name,
        type_code=CODES.data_file,
    )))


def _delete_sms_content_events_schedules(domain_name):
    models = [
        'SMSContent', 'EmailContent', 'SMSSurveyContent',
        'IVRSurveyContent', 'SMSCallbackContent', 'CustomContent'
    ]
    filters = [
        'alertevent__schedule__domain',
        'timedevent__schedule__domain',
        'randomtimedevent__schedule__domain',
        'casepropertytimedevent__schedule__domain'
    ]
    _delete_filtered_models('scheduling', models, [
        Q(**{name: domain_name}) for name in filters
    ])


def _delete_django_users(domain_name):
    total, counts = User.objects.filter(
        username__contains=f"@{domain_name}.commcarehq.org"
    ).delete()
    logger.info("Deleted %s Django users", total)
    logger.info(counts)


def _delete_filtered_models(app_name, models, domain_filters):
    for model_name in models:
        model = apps.get_model(app_name, model_name)
        for q_filter in domain_filters:
            total, counts = model.objects.filter(q_filter).delete()
            if total:
                logger.info("Deleted %s", counts)

# We use raw queries instead of ORM because Django queryset delete needs to
# fetch objects into memory to send signals and handle cascades. It makes deletion very slow
# if we have a millions of rows in stock data tables.

DOMAIN_DELETE_OPERATIONS = [
    RawDeletion('stock', ['stocktransaction'], """
        DELETE FROM stock_stocktransaction
        WHERE report_id IN (SELECT id FROM stock_stockreport WHERE domain=%s)
    """),
    RawDeletion('stock', ['stockreport'], "DELETE FROM stock_stockreport WHERE domain=%s"),
    RawDeletion('commtrack', ['stockstate'], """
        DELETE FROM commtrack_stockstate
        WHERE product_id IN (SELECT product_id FROM products_sqlproduct WHERE domain=%s)
    """),
    CustomDeletion('auth', _delete_django_users, ['User']),
    ModelDeletion('products', 'SQLProduct', 'domain'),
    ModelDeletion('locations', 'SQLLocation', 'domain', ['LocationRelation']),
    ModelDeletion('locations', 'LocationType', 'domain'),
    ModelDeletion('stock', 'DocDomainMapping', 'domain_name'),
    ModelDeletion('domain_migration_flags', 'DomainMigrationProgress', 'domain'),
    ModelDeletion('sms', 'DailyOutboundSMSLimitReached', 'domain'),
    ModelDeletion('sms', 'SMS', 'domain'),
    ModelDeletion('sms', 'Email', 'domain'),
    ModelDeletion('sms', 'SQLLastReadMessage', 'domain'),
    ModelDeletion('sms', 'ExpectedCallback', 'domain'),
    ModelDeletion('ivr', 'Call', 'domain'),
    ModelDeletion('sms', 'Keyword', 'domain', ['KeywordAction']),
    ModelDeletion('sms', 'PhoneNumber', 'domain'),
    ModelDeletion('sms', 'MessagingSubEvent', 'parent__domain'),
    ModelDeletion('sms', 'MessagingEvent', 'domain'),
    ModelDeletion('sms', 'QueuedSMS', 'domain'),
    ModelDeletion('sms', 'PhoneBlacklist', 'domain'),
    CustomDeletion('sms', _delete_domain_backend_mappings, ['SQLMobileBackendMapping']),
    ModelDeletion('sms', 'MobileBackendInvitation', 'domain'),
    CustomDeletion('sms', _delete_domain_backends, ['SQLMobileBackend']),
    CustomDeletion('users', _delete_web_user_membership, []),
    CustomDeletion('accounting', _terminate_subscriptions, ['Subscription']),
    CustomDeletion('form_processor', _delete_all_cases, ['CommCareCaseSQL']),
    CustomDeletion('form_processor', _delete_all_forms, ['XFormInstanceSQL']),
    ModelDeletion('aggregate_ucrs', 'AggregateTableDefinition', 'domain', [
        'PrimaryColumn', 'SecondaryColumn', 'SecondaryTableDefinition', 'TimeAggregationDefinition',
    ]),
    ModelDeletion('app_manager', 'AppReleaseByLocation', 'domain'),
    ModelDeletion('app_manager', 'LatestEnabledBuildProfiles', 'domain'),
    ModelDeletion('app_manager', 'ResourceOverride', 'domain'),
    ModelDeletion('app_manager', 'GlobalAppConfig', 'domain'),
    ModelDeletion('case_importer', 'CaseUploadRecord', 'domain', [
        'CaseUploadFileMeta', 'CaseUploadFormRecord'
    ]),
    ModelDeletion('case_search', 'CaseSearchConfig', 'domain'),
    ModelDeletion('case_search', 'FuzzyProperties', 'domain'),
    ModelDeletion('case_search', 'IgnorePatterns', 'domain'),
    ModelDeletion('cloudcare', 'ApplicationAccess', 'domain', ['SQLAppGroup']),
    ModelDeletion('consumption', 'DefaultConsumption', 'domain'),
    ModelDeletion('custom_data_fields', 'CustomDataFieldsDefinition', 'domain', ['CustomDataFieldsProfile', 'Field']),
    ModelDeletion('data_analytics', 'GIRRow', 'domain_name'),
    ModelDeletion('data_analytics', 'MALTRow', 'domain_name'),
    ModelDeletion('data_dictionary', 'CaseType', 'domain', ['CaseProperty']),
    ModelDeletion('data_interfaces', 'ClosedParentDefinition', 'caserulecriteria__rule__domain'),
    ModelDeletion('data_interfaces', 'CustomMatchDefinition', 'caserulecriteria__rule__domain'),
    ModelDeletion('data_interfaces', 'MatchPropertyDefinition', 'caserulecriteria__rule__domain'),
    ModelDeletion('data_interfaces', 'CustomActionDefinition', 'caseruleaction__rule__domain'),
    ModelDeletion('data_interfaces', 'UpdateCaseDefinition', 'caseruleaction__rule__domain'),
    ModelDeletion('data_interfaces', 'CreateScheduleInstanceActionDefinition', 'caseruleaction__rule__domain'),
    ModelDeletion('data_interfaces', 'CaseRuleAction', 'rule__domain'),
    ModelDeletion('data_interfaces', 'CaseRuleCriteria', 'rule__domain'),
    ModelDeletion('data_interfaces', 'CaseRuleSubmission', 'rule__domain'),
    ModelDeletion('data_interfaces', 'CaseRuleSubmission', 'domain'),  # TODO
    ModelDeletion('data_interfaces', 'AutomaticUpdateRule', 'domain'),
    ModelDeletion('data_interfaces', 'DomainCaseRuleRun', 'domain'),
    ModelDeletion('integration', 'DialerSettings', 'domain'),
    ModelDeletion('integration', 'GaenOtpServerSettings', 'domain'),
    ModelDeletion('integration', 'HmacCalloutSettings', 'domain'),
    ModelDeletion('integration', 'SimprintsIntegration', 'domain'),
    ModelDeletion('linked_domain', 'DomainLink', 'linked_domain', ['DomainLinkHistory']),
    CustomDeletion('scheduling', _delete_sms_content_events_schedules, [
        'SMSContent', 'EmailContent', 'SMSSurveyContent',
        'IVRSurveyContent', 'SMSCallbackContent', 'CustomContent'
    ]),
    ModelDeletion('scheduling', 'MigratedReminder', 'broadcast__domain'),
    ModelDeletion('scheduling', 'MigratedReminder', 'rule__domain'),
    ModelDeletion('scheduling', 'AlertEvent', 'schedule__domain'),
    ModelDeletion('scheduling', 'TimedEvent', 'schedule__domain'),
    ModelDeletion('scheduling', 'RandomTimedEvent', 'schedule__domain'),
    ModelDeletion('scheduling', 'CasePropertyTimedEvent', 'schedule__domain'),
    ModelDeletion('scheduling', 'AlertSchedule', 'domain'),
    ModelDeletion('scheduling', 'ScheduledBroadcast', 'domain'),
    ModelDeletion('scheduling', 'ImmediateBroadcast', 'domain'),
    ModelDeletion('scheduling', 'TimedSchedule', 'domain'),
    PartitionedModelDeletion('scheduling_partitioned', 'AlertScheduleInstance', 'domain'),
    PartitionedModelDeletion('scheduling_partitioned', 'CaseAlertScheduleInstance', 'domain'),
    PartitionedModelDeletion('scheduling_partitioned', 'CaseTimedScheduleInstance', 'domain'),
    PartitionedModelDeletion('scheduling_partitioned', 'TimedScheduleInstance', 'domain'),
    ModelDeletion('domain', 'TransferDomainRequest', 'domain'),
    ModelDeletion('export', 'EmailExportWhenDoneRequest', 'domain'),
    ModelDeletion('export', 'LedgerSectionEntry', 'domain'),
    ModelDeletion('export', 'IncrementalExport', 'domain', ['IncrementalExportCheckpoint']),
    CustomDeletion('export', _delete_data_files, []),
    ModelDeletion('locations', 'LocationFixtureConfiguration', 'domain'),
    ModelDeletion('mobile_auth', 'SQLMobileAuthKeyRecord', 'domain'),
    ModelDeletion('ota', 'MobileRecoveryMeasure', 'domain'),
    ModelDeletion('ota', 'SerialIdBucket', 'domain'),
    ModelDeletion('ota', 'DeviceLogRequest', 'domain'),
    ModelDeletion('phone', 'OwnershipCleanlinessFlag', 'domain'),
    ModelDeletion('phone', 'SyncLogSQL', 'domain'),
    ModelDeletion('phonelog', 'ForceCloseEntry', 'domain'),
    ModelDeletion('phonelog', 'UserErrorEntry', 'domain'),
    ModelDeletion('registration', 'RegistrationRequest', 'domain'),
    ModelDeletion('reminders', 'EmailUsage', 'domain'),
    ModelDeletion('reports', 'ReportsSidebarOrdering', 'domain'),
    ModelDeletion('smsforms', 'SQLXFormsSession', 'domain'),
    ModelDeletion('translations', 'TransifexOrganization', 'transifexproject__domain'),
    ModelDeletion('translations', 'SMSTranslations', 'domain'),
    ModelDeletion('translations', 'TransifexBlacklist', 'domain'),
    ModelDeletion('translations', 'TransifexProject', 'domain'),
    ModelDeletion('userreports', 'AsyncIndicator', 'domain'),
    ModelDeletion('userreports', 'DataSourceActionLog', 'domain'),
    ModelDeletion('userreports', 'InvalidUCRData', 'domain'),
    ModelDeletion('userreports', 'ReportComparisonDiff', 'domain'),
    ModelDeletion('userreports', 'ReportComparisonException', 'domain'),
    ModelDeletion('userreports', 'ReportComparisonTiming', 'domain'),
    ModelDeletion('users', 'DomainRequest', 'domain'),
    ModelDeletion('users', 'Invitation', 'domain'),
    ModelDeletion('users', 'DomainPermissionsMirror', 'source'),
    ModelDeletion('users', 'UserReportingMetadataStaging', 'domain'),
    ModelDeletion('user_importer', 'UserUploadRecord', 'domain'),
    ModelDeletion('zapier', 'ZapierSubscription', 'domain'),
    ModelDeletion('dhis2', 'Dhis2Connection', 'domain'),
    ModelDeletion('motech', 'RequestLog', 'domain'),
    ModelDeletion('motech', 'ConnectionSettings', 'domain'),
    ModelDeletion('couchforms', 'UnfinishedSubmissionStub', 'domain'),
    ModelDeletion('couchforms', 'UnfinishedArchiveStub', 'domain'),
    CustomDeletion('ucr', delete_all_ucr_tables_for_domain, []),
]

def apply_deletion_operations(domain_name):
    raw_ops, model_ops = _split_ops_by_type(DOMAIN_DELETE_OPERATIONS)

    with connection.cursor() as cursor:
        for op in raw_ops:
            op.execute(cursor, domain_name)

    for op in model_ops:
        op.execute(domain_name)


def _split_ops_by_type(ops):
    raw_ops = []
    model_ops = []
    for op in ops:
        if isinstance(op, RawDeletion):
            raw_ops.append(op)
        else:
            model_ops.append(op)
    return raw_ops, model_ops
