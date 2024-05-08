"""Reuse databases between test runs to save setup/teardown time.

In addition to the normal django database setup/teardown, also
setup/teardown Couch and Elasticsearch databases. Database setup/
teardown may be skipped, depending on the presence and value of an
environment variable (`REUSE_DB`) or option (`--reusedb`). Typical
usage is `REUSE_DB=1` which means skip database setup and migrations
if possible and do not teardown databases after running tests. If
connection fails for any test database in `settings.DATABASES` all
databases will be re-created and migrated.

The `REUSE_DB` environment variable may be overridden with
`--reusedb` option passed on the command line.
"""
import logging
import os
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from pytest_django import fixtures as django_fixtures
from unmagic import get_request, use

from django.conf import settings
from django.core import cache
from django.core.management import call_command
from django.db.backends.base.creation import TEST_DATABASE_PREFIX
from django.db.utils import OperationalError
from django.test import utils as djutils
from django.test.utils import get_unique_databases_and_mirrors

from couchdbkit import ResourceNotFound
from requests.exceptions import HTTPError

from corehq.util.test_utils import timelimit, unit_testing_only

from .util import override_fixture
from ..tools import nottest

log = logging.getLogger(__name__)

REUSE_DB_HELP = """
To be used in conjunction with the environment variable REUSE_DB=1.
reset: Drop existing test dbs, then create and migrate new ones, but do not
    teardown after running tests. This is convenient when the existing databases
    are outdated and need to be rebuilt.
flush: Flush all objects from the old test databases before running tests.
    Much faster than `reset`. Also runs `bootstrap` (see below).
bootstrap: Restore database state such as software plan versions and currencies
    initialized by database migrations. Sometimes when running tests with
    REUSE_DB=1 this state is lost, causing tests that depend on it to fail.
migrate: Migrate the test databases before running tests.
teardown: Skip database setup; do normal teardown after running tests.
"""
SETUP_DATABASES_FUNCTION_NAME = f"{__name__} setup_databases"


@pytest.hookimpl
def pytest_addoption(parser):
    parser.addoption(
        "--reusedb",
        default=os.environ.get("REUSE_DB"),
        help=REUSE_DB_HELP,
    )
    parser.addoption(
        "--db",
        default="both",
        choices=["skip", "only"],
        help="Skip or only run database tests."
    )


@pytest.hookimpl
def pytest_configure(config):
    config.reuse_db = reusedb = config.getoption("--reusedb")
    config.skip_setup_for_reuse_db = reusedb and reusedb != "reset"
    config.should_teardown = not reusedb or reusedb == "teardown"
    db_opt = config.getoption("--db")
    assert db_opt in ["both", "only", "skip"], db_opt
    config.should_run_database_tests = db_opt


@pytest.hookimpl(wrapper=True)
def pytest_collection_modifyitems(session, items):
    """Sort and filter tests, inject database setup"""
    import pytest_django.plugin as mod
    django_key = None

    class items_for_django:
        def sort(key):
            nonlocal django_key
            django_key = key
            filter_and_sort(items, key, session)

    def skip_django_modifyitems():
        called.append(1)
        return False

    mod.pytest_collection_modifyitems(items_for_django)
    called = []
    # use patch to skip django-pytest pytest_collection_modifyitems
    with patch.object(mod, "django_settings_is_configured", skip_django_modifyitems):
        yield
    assert called, "django_settings_is_configured patch was ineffective. " \
        "HQ-speicific test filtering and sorting may not have happened."
    assert is_still_sorted(items, django_key), "Test order changed. Database " \
        "setup may not be done at the correct point in the test run."


def filter_and_sort(items, key, session):
    def is_db_test(item):
        return bool(new_key(item))

    new_key = reorder(key)
    if session.config.should_run_database_tests == "only":
        should_run = is_db_test
    elif session.config.should_run_database_tests == "skip":
        def should_run(item):
            return not is_db_test(item)
    else:
        def should_run(item):
            return True

    tests = sorted((t for t in items if should_run(t)), key=new_key)
    if session.config.should_run_database_tests != "skip":
        _db_context.setup_before_first_db_test(tests, is_db_test, session)
    items[:] = tests


def reorder(key):
    """Translate django-pytest's test sorting key

    - 2 -> 0: non-db tests first (pytest-django normally runs them last)
    -      1: DeferredDatabaseContext.setup_databases
    - 0 -> 2: TestCase
    - 1 -> 3: TransactionTestCase last
    """
    def is_setup(item):
        return item.name == SETUP_DATABASES_FUNCTION_NAME

    def new_key(item):
        fixtures = {f._id for f in getattr(item.obj, "unmagic_fixtures", [])}
        if "transactional_db" in fixtures:
            return 3
        if "db" in fixtures:
            return 2
        return 1 if is_setup(item) else new_order[key(item)]

    new_order = {2: 0, 0: 2, 1: 3}
    return new_key


def is_still_sorted(items, key):
    if not items:
        return True
    new_key = reorder(key)
    it = iter(items)
    next(it)
    return all(new_key(a) <= new_key(b) for a, b in zip(items, it))


@override_fixture(django_fixtures.django_db_setup)
@use("django_db_modify_db_settings")
def django_db_setup():
    """Override pytest-django's django_db_setup fixture

    Replace pytest-django's database setup/teardown with
    DeferredDatabaseContext, which handles other databases
    including Couch, Elasticsearch, BlobDB, and Redis.
    """
    try:
        yield
    finally:
        _db_context.teardown_databases()


class DeferredDatabaseContext:

    def setup_before_first_db_test(self, tests, is_db_test, session):
        """Inject database setup just before the first test that needs it

        Allows expensive setup to be avoided when there are no database
        tests included in the test run. Database tests will not be run if
        database setup fails.
        """
        setup = pytest.Function.from_parent(
            pytest.Module.from_parent(session, path=Path(__file__), nodeid="reusedb"),
            name=SETUP_DATABASES_FUNCTION_NAME,
            callobj=lambda: self.setup_databases(session),
        )
        for i, test in enumerate(tests):
            if is_db_test(test):
                tests.insert(i, setup)
                break

    @timelimit(480)
    def setup_databases(self, session):
        """Setup databases for tests"""
        from corehq.blobs.tests.util import TemporaryFilesystemBlobDB

        def setup(enter, cleanup):
            # NOTE teardowns will be called in reverse order
            enter(TemporaryFilesystemBlobDB())
            cleanup(delete_elastic_indexes)
            enter(couch_sql_context(session.config))
            if session.config.should_teardown:
                cleanup(close_leaked_sql_connections)
                cleanup(clear_redis)
                cleanup(delete_couch_databases)

        assert "teardown_databases" not in self.__dict__, "already set up"
        db_blocker = get_request().getfixturevalue("django_db_blocker")
        with db_blocker.unblock(), ExitStack() as stack:
            try:
                setup(stack.enter_context, stack.callback)
            except BaseException:
                session.shouldfail = "Abort: database setup failed"
                raise
            self.teardown_databases = stack.pop_all().close

    def teardown_databases(self):
        """No-op to be replaced with ExitStack.close by setup_databases"""


@unit_testing_only
@contextmanager
def couch_sql_context(config):
    if config.skip_setup_for_reuse_db and sql_databases_ok():
        if config.reuse_db == "migrate":
            call_command('migrate_multi', interactive=False)
        if config.reuse_db == "flush":
            flush_databases()
        if config.reuse_db == "bootstrap":
            bootstrap_migrated_db_state()
        if config.should_teardown:
            dbs = get_sql_databases()
    else:
        if config.reuse_db == "reset":
            reset_databases(config.option.verbose)
        dbs = djutils.setup_databases(
            interactive=False,
            verbosity=config.option.verbose,
            # avoid re-creating databases that already exist
            keepdb=config.skip_setup_for_reuse_db,
        )

    try:
        yield
    finally:
        if config.should_teardown:
            djutils.teardown_databases(
                reversed(dbs),  # tear down in reverse setup order
                verbosity=config.option.verbose,
            )


def sql_databases_ok():
    for connection, db_name, _ in get_sql_databases():
        try:
            connection.ensure_connection()
        except OperationalError as e:
            print(str(e), file=sys.__stderr__)
            return False
    return True


def get_sql_databases(*, _cache=[]):
    if not _cache:
        from django.db import connections
        test_databases, mirrored_aliases = get_unique_databases_and_mirrors()
        assert not mirrored_aliases, "DB mirrors not supported"
        for signature, (db_name, aliases) in test_databases.items():
            alias = list(aliases)[0]
            connection = connections[alias]
            db = connection.settings_dict
            assert db["NAME"].startswith(TEST_DATABASE_PREFIX), db["NAME"]
            _cache.append((connection, db_name, True))
    return _cache


@unit_testing_only
def reset_databases(verbosity):
    delete_couch_databases()
    delete_elastic_indexes()
    clear_redis()
    # tear down all databases together to avoid dependency issues
    teardown = []
    for connection, db_name, is_first in get_sql_databases():
        try:
            connection.ensure_connection()
            teardown.append((connection, db_name, is_first))
        except OperationalError:
            pass  # ignore missing database
    djutils.teardown_databases(reversed(teardown), verbosity=verbosity)


@unit_testing_only
def delete_couch_databases():
    for db in get_all_couch_dbs():
        try:
            db.server.delete_db(db.dbname)
            log.info("deleted database %s", db.dbname)
        except ResourceNotFound:
            log.info("database %s not found! it was probably already deleted.", db.dbname)


@unit_testing_only
def delete_elastic_indexes():
    from corehq.apps.es.client import manager as elastic_manager
    # corehq.apps.es.client.create_document_adapter uses
    # TEST_DATABASE_PREFIX when constructing test index names
    for index_name in elastic_manager.get_indices():
        if index_name.startswith(TEST_DATABASE_PREFIX):
            elastic_manager.index_delete(index_name)


@unit_testing_only
def clear_redis():
    config = settings.CACHES.get("redis", {})
    loc = config.get("TEST_LOCATION")
    if loc:
        redis = cache.caches['redis']
        assert redis.client._server == [loc], (redis.client._server, config)
        redis.clear()


@nottest
@unit_testing_only
def get_all_couch_dbs():
    from corehq.util.couchdb_management import couch_config
    all_dbs = list(couch_config.all_dbs_by_db_name.values())
    for db in all_dbs:
        if '/test_' not in db.uri:
            raise ValueError("not a test db url: db=%s url=%r" % (db.dbname, db.uri))
    return all_dbs


def close_leaked_sql_connections():
    from corehq.sql_db.connections import connection_manager
    connection_manager.dispose_all()


@unit_testing_only
def flush_databases():
    """
    Best effort at emptying all documents from all databases.
    Useful when you break a test and it doesn't clean up properly. This took
    about 5 seconds to run when trying it out.
    """
    print("Flushing test databases, check yourself before you wreck yourself!", file=sys.__stdout__)
    for db in get_all_couch_dbs():
        try:
            db.flush()
        except (ResourceNotFound, HTTPError):
            pass
    call_command('flush', interactive=False)
    bootstrap_migrated_db_state()


@unit_testing_only
def bootstrap_migrated_db_state():
    from corehq.apps.accounting.tests.generator import bootstrap_accounting
    from corehq.apps.smsbillables.tests.utils import bootstrap_smsbillables
    bootstrap_accounting()
    bootstrap_smsbillables()


_db_context = DeferredDatabaseContext()
