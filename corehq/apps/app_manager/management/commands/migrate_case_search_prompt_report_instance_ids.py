import re

from corehq.apps.app_manager.fixtures.mobile_ucr import (
    ReportFixturesProviderV2,
)
from corehq.apps.app_manager.management.commands.helpers import (
    AppMigrationCommandBase,
)
from corehq.toggles import SYNC_SEARCH_CASE_CLAIM


class Command(AppMigrationCommandBase):
    help = """One-time migration to add 'commcare-reports:' prefix to
    report instance IDs in case search itemset prompts"""

    chunk_size = 1
    include_builds = True
    include_linked_apps = True

    def migrate_app(self, app_doc):
        should_save = False
        for module in app_doc.get('modules', []):
            if module.get('search_config'):
                properties = module.get('search_config').get('properties')
                if not properties:
                    continue
                for prop in properties:
                    should_save |= update_itemset(prop, self.log_debug)

        return app_doc if should_save else None

    def get_domains(self):
        return sorted(SYNC_SEARCH_CASE_CLAIM.get_enabled_domains())


def update_itemset(prop, debug):
    itemset = prop.get('itemset')
    if not itemset:
        return False

    instance_uri = itemset.get('instance_uri')
    if not (instance_uri and instance_uri.startswith(f'jr://fixture/{ReportFixturesProviderV2.id}:')):
        return False

    should_save = False
    instance_id = itemset.get('instance_id')
    if instance_id and ReportFixturesProviderV2.id not in instance_id:
        should_save = True
        new_instance_id = f'{ReportFixturesProviderV2.id}:{instance_id}'
        itemset['instance_id'] = new_instance_id
        nodeset = itemset['nodeset']
        new_nodeset = re.sub(r"instance\((.)" + instance_id,
                     r"instance(\1" + ReportFixturesProviderV2.id + r":" + instance_id,
                     (itemset.get('nodeset') or ''))
        itemset['nodeset'] = new_nodeset

        if debug:
            print(instance_id, "", new_instance_id)
            print(nodeset, "", new_nodeset)
    return should_save
