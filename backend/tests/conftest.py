import os


_TEST_MODE_ENV = "MI_AI_TEST_MODE"


def _activate_test_mode(environment):
    original = (_TEST_MODE_ENV in environment, environment.get(_TEST_MODE_ENV))
    environment[_TEST_MODE_ENV] = "1"
    return original


def _restore_test_mode(environment, original):
    was_present, value = original
    if was_present:
        environment[_TEST_MODE_ENV] = value
    else:
        environment.pop(_TEST_MODE_ENV, None)


_INITIAL_TEST_MODE = _activate_test_mode(os.environ)

import sys

try:
    from google.cloud.firestore_v1.client import Client as _GoogleFirestoreClient
except ImportError:
    _GOOGLE_FIRESTORE_CLIENT_TYPES = ()
else:
    _GOOGLE_FIRESTORE_CLIENT_TYPES = (_GoogleFirestoreClient,)


def _quarantine_cached_app_clients(modules):
    quarantined = []
    seen = set()
    for module_name in ("backend.app", "app"):
        module = modules.get(module_name)
        if module is None or id(module) in seen:
            continue
        seen.add(id(module))
        database = getattr(module, "MI_FIREBASE_DB", None)
        if isinstance(database, _GOOGLE_FIRESTORE_CLIENT_TYPES):
            module.MI_FIREBASE_DB = None
            quarantined.append((module, database))
    return quarantined


def _restore_cached_app_clients(quarantined):
    for module, database in quarantined:
        module.MI_FIREBASE_DB = database


def _finish_test_session(environment, original_test_mode, quarantined):
    try:
        _restore_cached_app_clients(quarantined)
    finally:
        _restore_test_mode(environment, original_test_mode)


_QUARANTINED_APP_CLIENTS = _quarantine_cached_app_clients(sys.modules)
_SESSION_COUNT = 0

import pytest


def _blocked_firestore_client(*args, **kwargs):
    raise RuntimeError(
        "Firestore client creation is disabled in tests; inject a fake database."
    )


@pytest.hookimpl(trylast=True)
def pytest_sessionstart(session):
    global _INITIAL_TEST_MODE, _QUARANTINED_APP_CLIENTS, _SESSION_COUNT
    if _SESSION_COUNT:
        _INITIAL_TEST_MODE = _activate_test_mode(os.environ)
    _QUARANTINED_APP_CLIENTS.extend(
        _quarantine_cached_app_clients(sys.modules)
    )
    _SESSION_COUNT += 1


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    _finish_test_session(
        os.environ,
        _INITIAL_TEST_MODE,
        _QUARANTINED_APP_CLIENTS,
    )


@pytest.fixture(autouse=True)
def block_firestore_client(monkeypatch):
    try:
        from firebase_admin import firestore
    except ImportError:
        return

    monkeypatch.setattr(firestore, "client", _blocked_firestore_client)


@pytest.fixture
def fake_firestore(request):
    fake_type = getattr(request.module, "_FakeFirestore", None)
    if fake_type is None:
        raise RuntimeError(
            "This test module must define _FakeFirestore to use the fake_firestore fixture."
        )
    return fake_type()
