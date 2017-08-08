import csv
import json

from django.core.management.base import BaseCommand

from corehq.form_processor.interfaces.dbaccessors import CaseAccessors
from corehq.util.log import with_progress_bar
from corehq.motech.repeaters.dbaccessors import iter_repeat_records_by_domain, get_repeat_record_count
from custom.enikshay.case_utils import get_person_case_from_voucher
from corehq.apps.users.models import CommCareUser


class Command(BaseCommand):
    help = """
    Output 3 CSV files of voucher cases that were sent to BETS in repeater <repeater_id>.
    The second file contains a list of duplicate voucher ids which should be handled manually.
    The third file contains a list of errored cases.

    This should be run twice, once for Chemist vouchers, and once for Lab vouchers.
    """

    def add_arguments(self, parser):
        parser.add_argument('domain')
        parser.add_argument('repeater_id')
        parser.add_argument('filename')

    def handle(self, domain, repeater_id, filename, **options):
        accessor = CaseAccessors(domain)
        records = iter_repeat_records_by_domain(domain, repeater_id=repeater_id)
        record_count = get_repeat_record_count(domain, repeater_id=repeater_id)

        row_names = [
            'VoucherID',
            'EventOccurDate',
            'EventID',
            'BeneficiaryUUID',
            'BeneficiaryType',
            'Location',
            'Amount',
            'DTOLocation',
            'InvestigationType',
            'PersonId',
            'AgencyId',
            'EnikshayApprover',
            'EnikshayRole',
            'EnikshayApprovalDate',
            'Succeeded',    # Some records did succeed when we sent them.
                            # Include this so they don't re-pay people.
        ]

        seen_voucher_ids = set()
        duplicate_voucher_ids = set()
        errors = []
        with open(filename, 'w') as f:
            writer = csv.writer(f)
            writer.writerow(row_names)

            for record in with_progress_bar(records, length=record_count):
                try:
                    payload = json.loads(record.get_payload())['voucher_details'][0]

                    voucher_id = record.payload_id
                    person_case = get_person_case_from_voucher(domain, voucher_id)
                    voucher_case = accessor.get_case(voucher_id)
                    payload[u'PersonId'] = person_case.case_id
                    payload[u'AgencyId'] = voucher_case.get_case_property('voucher_fulfilled_by_id')

                    approver_id = voucher_case.get_case_property('voucher_approved_by_id')
                    approver = CommCareUser.get_by_user_id(approver_id)
                    payload[u'EnikshayApprover'] = approver.name
                    payload[u'EnikshayRole'] = approver.user_data.get('usertype')
                    payload[u'EnikshayApprovalDate'] = voucher_case.get_case_property('date_approved')

                    payload['Succeeded'] = record.succeeded

                except Exception as e:
                    errors.append([record.payload_id, unicode(e)])
                    continue
                if voucher_id in seen_voucher_ids:
                    duplicate_voucher_ids.add(voucher_id)
                else:
                    seen_voucher_ids.add(voucher_id)
                row = [
                    payload.get(name) if payload.get(name) is not None else ""
                    for name in row_names
                ]
                writer.writerow(row)

        print "{} duplicates found".format(len(duplicate_voucher_ids))
        if duplicate_voucher_ids:
            with open('duplicates_{}'.format(filename), 'w') as f:
                writer = csv.writer(f)
                for duplicate_id in duplicate_voucher_ids:
                    writer.write_row([duplicate_id])

        print "{} errors".format(len(errors))
        if errors:
            with open('errors_{}'.format(filename), 'w') as f:
                writer = csv.writer(f)
                writer.write_row(['episode_id', 'error'])
                for error in errors:
                    writer.write_row(errors)
