import json
from importlib import import_module
from types import SimpleNamespace

import pytest


PRODUCTION_PROJECT_ID = "mi-ai-b3a57"
STAGING_PROJECT_ID = "mi-ai-whatsapp-staging"


def _app_module():
    return import_module("backend.app")


def _set_project_environment(monkeypatch, project_id=None, cloud_project=None):
    monkeypatch.setenv("MI_FIREBASE_ENVIRONMENT", "staging")
    if project_id is None:
        monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    else:
        monkeypatch.setenv("FIREBASE_PROJECT_ID", project_id)
    if cloud_project is None:
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    else:
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", cloud_project)


@pytest.mark.parametrize(
    "project_id",
    [PRODUCTION_PROJECT_ID, "unrecognized-project"],
)
def test_staging_rejects_non_staging_project_ids(monkeypatch, project_id):
    app_module = _app_module()
    _set_project_environment(monkeypatch, project_id)

    with pytest.raises(RuntimeError, match="does not match the staging project"):
        app_module._resolve_firebase_project_id()


def test_staging_requires_project_id_and_never_uses_production_fallback(
    monkeypatch,
):
    app_module = _app_module()
    _set_project_environment(
        monkeypatch,
        cloud_project=PRODUCTION_PROJECT_ID,
    )

    with pytest.raises(RuntimeError, match="requires an explicit FIREBASE_PROJECT_ID"):
        app_module._resolve_firebase_project_id()


def test_valid_staging_project_ignores_google_cloud_project(monkeypatch):
    app_module = _app_module()
    _set_project_environment(
        monkeypatch,
        STAGING_PROJECT_ID,
        PRODUCTION_PROJECT_ID,
    )

    assert app_module._resolve_firebase_project_id() == STAGING_PROJECT_ID


def test_invalid_environment_selector_fails_closed(monkeypatch):
    app_module = _app_module()
    monkeypatch.setenv("MI_FIREBASE_ENVIRONMENT", "preview")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", STAGING_PROJECT_ID)

    with pytest.raises(RuntimeError, match="must be staging or production"):
        app_module._resolve_firebase_project_id()


def test_legacy_production_project_selection_is_preserved(monkeypatch):
    app_module = _app_module()
    monkeypatch.delenv("MI_FIREBASE_ENVIRONMENT", raising=False)
    monkeypatch.setenv("FIREBASE_PROJECT_ID", PRODUCTION_PROJECT_ID)
    assert app_module._resolve_firebase_project_id() == PRODUCTION_PROJECT_ID

    monkeypatch.delenv("FIREBASE_PROJECT_ID")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", PRODUCTION_PROJECT_ID)
    assert app_module._resolve_firebase_project_id() == PRODUCTION_PROJECT_ID

    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT")
    assert (
        app_module._resolve_firebase_project_id()
        == app_module.MI_FIREBASE_LEGACY_PROJECT_ID
    )


@pytest.mark.parametrize("environment", [None, "production"])
def test_staging_project_requires_staging_selector(monkeypatch, environment):
    app_module = _app_module()
    if environment is None:
        monkeypatch.delenv("MI_FIREBASE_ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("MI_FIREBASE_ENVIRONMENT", environment)
    monkeypatch.setenv("FIREBASE_PROJECT_ID", STAGING_PROJECT_ID)

    with pytest.raises(
        RuntimeError,
        match="requires MI_FIREBASE_ENVIRONMENT=staging",
    ):
        app_module._resolve_firebase_project_id()


def test_service_account_json_is_validated_without_exposing_contents(monkeypatch):
    app_module = _app_module()
    monkeypatch.setenv("MI_AI_TEST_MODE", "0")
    monkeypatch.setattr(app_module, "MI_FIREBASE_PROJECT_ID", STAGING_PROJECT_ID)
    monkeypatch.setenv(
        "FIREBASE_SERVICE_ACCOUNT_JSON",
        json.dumps({"project_id": STAGING_PROJECT_ID}),
    )
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    credential = SimpleNamespace(project_id=STAGING_PROJECT_ID)
    monkeypatch.setattr(
        app_module.firebase_admin_credentials,
        "Certificate",
        lambda source: credential,
    )

    assert app_module.mi_load_firebase_credential() is credential


@pytest.mark.parametrize(
    "raw_json",
    ["{invalid", json.dumps(["not", "an", "object"])],
)
def test_invalid_service_account_json_fails_safely(monkeypatch, raw_json):
    app_module = _app_module()
    monkeypatch.setenv("MI_AI_TEST_MODE", "0")
    monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT_JSON", raw_json)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(app_module, "MI_FIREBASE_PROJECT_ID", STAGING_PROJECT_ID)

    with pytest.raises(RuntimeError, match="FIREBASE_SERVICE_ACCOUNT_JSON"):
        app_module.mi_load_firebase_credential()


def test_service_account_json_project_mismatch_is_rejected(monkeypatch):
    app_module = _app_module()
    monkeypatch.setenv("MI_AI_TEST_MODE", "0")
    monkeypatch.setenv(
        "FIREBASE_SERVICE_ACCOUNT_JSON",
        json.dumps({"project_id": PRODUCTION_PROJECT_ID}),
    )
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(app_module, "MI_FIREBASE_PROJECT_ID", STAGING_PROJECT_ID)
    monkeypatch.setattr(
        app_module.firebase_admin_credentials,
        "Certificate",
        lambda source: SimpleNamespace(project_id=source["project_id"]),
    )

    with pytest.raises(RuntimeError, match="does not match the configured project"):
        app_module.mi_load_firebase_credential()


def test_missing_service_account_file_fails_safely(monkeypatch):
    app_module = _app_module()
    monkeypatch.setenv("MI_AI_TEST_MODE", "0")
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "missing-staging-key.json")
    monkeypatch.setattr(app_module, "MI_FIREBASE_PROJECT_ID", STAGING_PROJECT_ID)
    monkeypatch.setattr(app_module.os.path, "isfile", lambda _path: False)

    with pytest.raises(RuntimeError, match="file was not found"):
        app_module.mi_load_firebase_credential()


def test_file_credential_project_mismatch_is_rejected(monkeypatch):
    app_module = _app_module()
    monkeypatch.setenv("MI_AI_TEST_MODE", "0")
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "staging-key.json")
    monkeypatch.setattr(app_module, "MI_FIREBASE_PROJECT_ID", STAGING_PROJECT_ID)
    monkeypatch.setattr(app_module.os.path, "isfile", lambda _path: True)
    monkeypatch.setattr(
        app_module.firebase_admin_credentials,
        "Certificate",
        lambda _path: SimpleNamespace(project_id=PRODUCTION_PROJECT_ID),
    )

    with pytest.raises(RuntimeError, match="does not match the configured project"):
        app_module.mi_load_firebase_credential()


def test_file_credential_with_matching_project_is_accepted(monkeypatch):
    app_module = _app_module()
    monkeypatch.setenv("MI_AI_TEST_MODE", "0")
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "staging-key.json")
    monkeypatch.setattr(app_module, "MI_FIREBASE_PROJECT_ID", STAGING_PROJECT_ID)
    monkeypatch.setattr(app_module.os.path, "isfile", lambda _path: True)
    credential = SimpleNamespace(project_id=STAGING_PROJECT_ID)
    monkeypatch.setattr(
        app_module.firebase_admin_credentials,
        "Certificate",
        lambda _path: credential,
    )

    assert app_module.mi_load_firebase_credential() is credential


def test_invalid_file_credential_error_does_not_expose_details(monkeypatch):
    app_module = _app_module()
    monkeypatch.setenv("MI_AI_TEST_MODE", "0")
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "staging-key.json")
    monkeypatch.setattr(app_module, "MI_FIREBASE_PROJECT_ID", STAGING_PROJECT_ID)
    monkeypatch.setattr(app_module.os.path, "isfile", lambda _path: True)

    def reject_credential(_path):
        raise ValueError("private-key-material")

    monkeypatch.setattr(
        app_module.firebase_admin_credentials,
        "Certificate",
        reject_credential,
    )
    with pytest.raises(RuntimeError) as error:
        app_module.mi_load_firebase_credential()

    assert "private-key-material" not in str(error.value)


def test_invalid_file_credential_shape_fails_safely(monkeypatch):
    app_module = _app_module()
    monkeypatch.setenv("MI_AI_TEST_MODE", "0")
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "staging-key.json")
    monkeypatch.setattr(app_module, "MI_FIREBASE_PROJECT_ID", STAGING_PROJECT_ID)
    monkeypatch.setattr(app_module.os.path, "isfile", lambda _path: True)

    def reject_shape(_path):
        raise AttributeError("invalid-json-shape")

    monkeypatch.setattr(
        app_module.firebase_admin_credentials,
        "Certificate",
        reject_shape,
    )

    with pytest.raises(RuntimeError, match="credentials are invalid") as error:
        app_module.mi_load_firebase_credential()

    assert "invalid-json-shape" not in str(error.value)


def test_staging_initialization_fails_closed_without_credentials(monkeypatch):
    app_module = _app_module()
    monkeypatch.setenv("MI_AI_TEST_MODE", "0")
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(app_module, "MI_AI_TEST_MODE", False)
    monkeypatch.setattr(app_module, "MI_FIREBASE_ENVIRONMENT", "staging")
    monkeypatch.setattr(app_module, "MI_FIREBASE_PROJECT_ID", STAGING_PROJECT_ID)
    initialize_calls = []
    monkeypatch.setattr(
        app_module,
        "firebase_admin",
        SimpleNamespace(_apps={}, initialize_app=lambda *args: initialize_calls.append(args)),
    )
    monkeypatch.setattr(app_module, "firebase_admin_auth", object())
    monkeypatch.setattr(app_module, "firebase_admin_credentials", object())
    monkeypatch.setattr(app_module, "firebase_admin_firestore", object())

    with pytest.raises(RuntimeError, match="Staging Firebase initialization failed"):
        app_module._initialize_firebase_admin()

    assert initialize_calls == []


def test_staging_rejects_an_unrelated_preinitialized_default_app(monkeypatch):
    app_module = _app_module()
    monkeypatch.setenv("MI_AI_TEST_MODE", "0")
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(app_module, "MI_AI_TEST_MODE", False)
    monkeypatch.setattr(app_module, "MI_FIREBASE_ENVIRONMENT", "staging")
    monkeypatch.setattr(app_module, "MI_FIREBASE_PROJECT_ID", STAGING_PROJECT_ID)
    unrelated_app = SimpleNamespace(
        project_id=PRODUCTION_PROJECT_ID,
        credential=SimpleNamespace(project_id=PRODUCTION_PROJECT_ID),
    )
    initialize_calls = []
    monkeypatch.setattr(
        app_module,
        "firebase_admin",
        SimpleNamespace(
            _apps={"[DEFAULT]": unrelated_app},
            get_app=lambda: unrelated_app,
            initialize_app=lambda *args: initialize_calls.append(args),
        ),
    )
    monkeypatch.setattr(app_module, "firebase_admin_auth", object())
    monkeypatch.setattr(app_module, "firebase_admin_credentials", object())
    monkeypatch.setattr(app_module, "firebase_admin_firestore", object())

    with pytest.raises(RuntimeError, match="Staging Firebase initialization failed"):
        app_module._initialize_firebase_admin()

    assert initialize_calls == []
    assert app_module.MI_FIREBASE_APP is None
    assert app_module.MI_FIREBASE_DB is None


@pytest.mark.parametrize(
    ("environment", "project_id"),
    [
        ("", PRODUCTION_PROJECT_ID),
        ("staging", STAGING_PROJECT_ID),
        ("production", PRODUCTION_PROJECT_ID),
    ],
)
def test_initialization_and_firestore_clients_use_the_selected_app(
    monkeypatch,
    environment,
    project_id,
):
    app_module = _app_module()
    monkeypatch.setenv("MI_AI_TEST_MODE", "0")
    monkeypatch.setattr(app_module, "MI_AI_TEST_MODE", False)
    monkeypatch.setattr(app_module, "MI_FIREBASE_ENVIRONMENT", environment)
    monkeypatch.setattr(app_module, "MI_FIREBASE_PROJECT_ID", project_id)

    expected_app = SimpleNamespace(project_id=project_id)
    fake_db = object()
    initialize_calls = []
    client_apps = []
    admin = SimpleNamespace(_apps={})

    def initialize_app(credential, options):
        initialize_calls.append((credential, options))
        admin._apps["[DEFAULT]"] = expected_app
        return expected_app

    admin.initialize_app = initialize_app
    admin.get_app = lambda: expected_app
    fake_firestore = SimpleNamespace(
        client=lambda *, app: client_apps.append(app) or fake_db
    )

    monkeypatch.setattr(app_module, "firebase_admin", admin)
    monkeypatch.setattr(app_module, "firebase_admin_auth", object())
    monkeypatch.setattr(app_module, "firebase_admin_credentials", object())
    monkeypatch.setattr(app_module, "firebase_admin_firestore", fake_firestore)
    monkeypatch.setattr(
        app_module,
        "mi_load_firebase_credential",
        lambda: SimpleNamespace(project_id=project_id),
    )
    monkeypatch.setitem(
        app_module.app.extensions,
        "firebase_admin_app",
        None,
    )

    app_module._initialize_firebase_admin()

    assert initialize_calls[0][1] == {"projectId": project_id}
    assert app_module.MI_FIREBASE_APP is expected_app
    assert app_module.app.extensions["firebase_admin_app"] is expected_app
    assert app_module.MI_FIREBASE_DB is fake_db
    assert client_apps == [expected_app]

    control_module = import_module("backend.chief_owner_control")
    rbac_module = import_module("backend.chief_owner_rbac")
    monkeypatch.setattr(control_module, "firestore", fake_firestore)
    monkeypatch.setattr(rbac_module, "firestore", fake_firestore)
    monkeypatch.setattr(rbac_module, "_firebase_ready", lambda: None)

    with app_module.app.app_context():
        assert control_module.database() is fake_db
        assert rbac_module.db() is fake_db

    assert client_apps == [expected_app, expected_app, expected_app]
