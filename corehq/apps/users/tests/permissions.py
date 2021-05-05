from django.test import SimpleTestCase, TestCase

import mock
from memoized import Memoized

from corehq.apps.export.views.utils import user_can_view_deid_exports
from corehq.apps.users.decorators import get_permission_name
from corehq.apps.users.models import (
    DomainMembership,
    Permissions,
    UserRole,
    WebUser,
)
from corehq.apps.users.permissions import DEID_EXPORT_PERMISSION, has_permission_to_view_report, \
    ODATA_FEED_PERMISSION, can_manage_releases
from corehq.util.test_utils import flag_enabled


class PermissionsTest(TestCase):

    def test_OR(self):
        p1 = Permissions(
            edit_web_users=True,
            view_web_users=True,
            view_roles=True,
            view_reports=True,
            view_report_list=['report1'],
        )
        p2 = Permissions(
            edit_apps=True,
            view_apps=True,
            view_reports=True,
            view_report_list=['report2'],
        )
        self.assertEqual(p1 | p2, Permissions(
            edit_apps=True,
            view_apps=True,
            edit_web_users=True,
            view_web_users=True,
            view_roles=True,
            view_reports=True,
            view_report_list=['report1', 'report2'],
        ))


@mock.patch('corehq.apps.export.views.utils.domain_has_privilege',
            lambda domain, privilege: True)
class PermissionsHelpersTest(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super(PermissionsHelpersTest, cls).setUpClass()
        cls.domain = 'export-permissions-test'
        cls.admin_domain = 'export-permissions-test-admin'
        cls.web_user = WebUser(username='temp@example.com', domains=[cls.domain, cls.admin_domain])
        cls.web_user.domain_memberships = [
            DomainMembership(domain=cls.domain, role_id='MYROLE'),
            DomainMembership(domain=cls.admin_domain, is_admin=True)
        ]
        cls.permissions = Permissions()

    def setUp(self):
        super(PermissionsHelpersTest, self).setUp()
        test_self = self

        def get_role(self, domain=None):
            return UserRole(
                domain=test_self.domain,
                permissions=test_self.permissions
            )

        assert hasattr(WebUser.has_permission, "get_cache"), "not memoized?"
        patches = [
            mock.patch.object(DomainMembership, 'role', property(get_role)),
            mock.patch.object(WebUser, 'get_role', get_role),
            mock.patch.object(WebUser, 'has_permission', WebUser.has_permission.__wrapped__),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        self.permissions = Permissions()
        super(PermissionsHelpersTest, self).tearDown()

    def test_deid_permission(self):
        self.assertFalse(user_can_view_deid_exports(self.domain, self.web_user))
        self.permissions = Permissions(view_report_list=[DEID_EXPORT_PERMISSION])
        self.assertTrue(
            self.permissions.has(get_permission_name(Permissions.view_report),
                                 data=DEID_EXPORT_PERMISSION))
        self.assertTrue(
            self.web_user.has_permission(
                self.domain, get_permission_name(Permissions.view_report),
                data=DEID_EXPORT_PERMISSION)
        )

        self.assertTrue(user_can_view_deid_exports(self.domain, self.web_user))

    def test_view_reports(self):
        self.assertFalse(self.web_user.can_view_reports(self.domain))
        self.permissions = Permissions(view_reports=True)
        self.assertTrue(self.web_user.can_view_reports(self.domain))

    def test_has_permission_to_view_report_all(self):
        self.assertFalse(has_permission_to_view_report(self.web_user, self.domain, ODATA_FEED_PERMISSION))
        self.permissions = Permissions(view_reports=True)
        self.assertTrue(has_permission_to_view_report(self.web_user, self.domain, ODATA_FEED_PERMISSION))

    def test_has_permission_to_view_report(self):
        self.assertFalse(has_permission_to_view_report(self.web_user, self.domain, ODATA_FEED_PERMISSION))
        self.permissions = Permissions(view_report_list=[ODATA_FEED_PERMISSION])
        self.assertTrue(has_permission_to_view_report(self.web_user, self.domain, ODATA_FEED_PERMISSION))

    @flag_enabled('RESTRICT_APP_RELEASE')
    def test_can_manage_releases_all(self):
        self.permissions = Permissions(manage_releases=False)    # manage_releases is True by default
        self.assertFalse(can_manage_releases(self.web_user, self.domain, "app_id"))
        self.permissions = Permissions()
        self.assertTrue(can_manage_releases(self.web_user, self.domain, "app_id"))

    @flag_enabled('RESTRICT_APP_RELEASE')
    def test_can_manage_releases(self):
        self.permissions = Permissions(manage_releases=False)  # manage_releases is True by default
        self.assertFalse(can_manage_releases(self.web_user, self.domain, "app_id"))
        self.permissions = Permissions(manage_releases=False, manage_releases_list=["app_id"])
        self.assertTrue(can_manage_releases(self.web_user, self.domain, "app_id"))

    @flag_enabled('RESTRICT_APP_RELEASE')
    def test_can_manage_releases_domain_admin(self):
        self.permissions = Permissions()
        self.assertTrue(can_manage_releases(self.web_user, self.domain, "app_id"))
        self.assertFalse(can_manage_releases(self.web_user, self.admin_domain, "app_id"))
