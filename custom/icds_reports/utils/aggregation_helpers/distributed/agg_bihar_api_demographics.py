
from custom.icds_reports.const import AGG_BIHAR_API_DEMOGRAPHICS, AGG_MIGRATION_TABLE
from custom.icds_reports.utils.aggregation_helpers.distributed.base import BaseICDSAggregationDistributedHelper
from corehq.apps.userreports.util import get_table_name
from dateutil.relativedelta import relativedelta
from custom.icds_reports.utils.aggregation_helpers import transform_day_to_month, month_formatter


class AggBiharApiDemographicsHelper(BaseICDSAggregationDistributedHelper):
    helper_key = 'agg-bihar_api_demographics'
    tablename = AGG_BIHAR_API_DEMOGRAPHICS

    def __init__(self, month):
        self.month = transform_day_to_month(month)
        self.end_date = transform_day_to_month(month + relativedelta(months=1, seconds=-1))

    def aggregate(self, cursor):
        drop_query, drop_params = self.drop_table_query()
        agg_query = self.aggregation_query()
        index_queries = self.indexes()

        cursor.execute(drop_query, drop_params)
        cursor.execute(agg_query)
        for query in index_queries:
            cursor.execute(query)

    def drop_table_query(self):
        return (
            'DELETE FROM "{}" WHERE month=%(month)s'.format(self.tablename),
            {'month': month_formatter(self.month)}
        )

    def aggregation_query(self):
        month_start_string = month_formatter(self.month)
        month_end_string = month_formatter(self.month + relativedelta(months=1, seconds=-1))
        person_case_ucr = get_table_name(self.domain, 'static-person_cases_v3')
        household_ucr = get_table_name(self.domain, 'static-household_cases')

        columns = (
            ('state_id', 'person_list.state_id'),
            ('district_id', 'person_list.district_id'),
            ('block_id', 'person_list.block_id'),
            ('supervisor_id', 'person_list.supervisor_id'),
            ('awc_id', 'person_list.awc_id'),
            ('month', f"'{month_start_string}'"),
            ('person_id', 'person_list.doc_id'),
            ('person_name', 'person_list.name'),
            ('has_adhaar', 'CASE WHEN person_list.aadhar_date is not null THEN 1 ELSE 0 END'),
            ('bank_account_number', 'person_list.bank_account_number'),
            ('ifsc_code', 'person_list.ifsc_code'),
            ('age_at_reg', 'person_list.age_at_reg'),
            ('dob', 'person_list.dob'),
            ('gender', 'person_list.sex'),
            ('blood_group', 'person_list.blood_group'),
            ('disabled', 'person_list.disabled'),
            ('disability_type', 'person_list.disability_type'),
            ('referral_status', 'person_list.referral_status'),
            ('migration_status', 'migration_tab.is_migrated'),
            ('resident', 'person_list.resident'),
            ('registered_status', 'person_list.registered_status'),
            ('rch_id', 'person_list.rch_id'),
            ('mcts_id', 'person_list.mcts_id'),
            ('phone_number', 'person_list.phone_number'),
            ('date_death', 'person_list.date_death'),
            ('site_death', 'person_list.site_death'),
            ('closed_on', 'person_list.closed_on'),
            ('reason_closure', 'person_list.reason_closure'),
            ('household_id', 'hh_list.doc_id'),
            ('household_name', 'hh_list.name'),
            ('hh_reg_date', 'hh_list.hh_reg_date'),
            ('hh_num', 'hh_list.hh_num'),
            ('hh_gps_location', 'hh_list.hh_gps_location'),
            ('hh_caste', 'hh_list.hh_caste'),
            ('hh_bpl_apl', 'hh_list.hh_bpl_apl'),
            ('hh_minority', 'hh_list.hh_minority'),
            ('hh_religion', 'hh_list.hh_religion'),

        )
        column_names = ", ".join([col[0] for col in columns])
        calculations = ", ".join([col[1] for col in columns])

        return f"""
                INSERT INTO "{self.tablename}" (
                    {column_names}
                )
                (
                SELECT
                {calculations}
                from "{person_case_ucr}" person_list
                LEFT JOIN "{AGG_MIGRATION_TABLE}" migration_tab ON (
                    person_list.doc_id = migration_tab.person_case_id AND
                    person_list.supervisor_id = migration_tab.supervisor_id AND
                    migration_tab.month='{month_start_string}'
                )
                LEFT JOIN "{household_ucr}" hh_list ON (
                    person_list.household_case_id = hh_list.doc_id AND
                    person_list.supervisor_id = hh_list.supervisor_id
                )
                WHERE (person_list.opened_on <= '{month_end_string}' AND
              (person_list.closed_on IS NULL OR person_list.closed_on >= '{month_start_string}' )) AND
              (
                migration_tab.is_migrated is distinct from 1 OR
                migration_tab.migration_date>='{month_start_string}')
              );
                """

    def indexes(self):
        return [
            'CREATE INDEX IF NOT EXISTS demographics_state_person_case_idx ON "{}" (month, state_id, person_id)'.format(self.tablename)
        ]
