import json
import hashlib
import hmac
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from importlib import import_module, reload
from threading import Barrier, Event, Lock, RLock, local
from types import SimpleNamespace
from unittest.mock import Mock
import pytest


def test_cached_firestore_client_is_rejected_but_fake_is_usable(monkeypatch):
    from google.cloud.firestore_v1.client import Client as FirestoreClient

    app_module = import_module("backend.app")
    cached_client = Mock(spec=FirestoreClient)
    monkeypatch.setattr(app_module, "MI_AI_TEST_MODE", False)
    monkeypatch.setattr(app_module, "MI_FIREBASE_DB", cached_client)

    with pytest.raises(RuntimeError, match="Cached Firestore clients are disabled"):
        app_module._firestore_database()

    fake_database = _FakeFirestore()
    monkeypatch.setattr(app_module, "MI_FIREBASE_DB", fake_database)
    assert app_module._firestore_database() is fake_database
    assert app_module.mi_owner_ref("test-owner").key == ("owners", "test-owner")


def test_conftest_quarantines_and_restores_cached_app_clients():
    from google.cloud.firestore_v1.client import Client as FirestoreClient

    test_config = import_module("backend.tests.conftest")
    cached_client = Mock(spec=FirestoreClient)
    app_module = SimpleNamespace(MI_FIREBASE_DB=cached_client)

    quarantined = test_config._quarantine_cached_app_clients(
        {"backend.app": app_module}
    )

    assert app_module.MI_FIREBASE_DB is None
    assert quarantined == [(app_module, cached_client)]
    test_config._restore_cached_app_clients(quarantined)
    assert app_module.MI_FIREBASE_DB is cached_client


@pytest.mark.parametrize("original_value", [None, "1"])
def test_test_mode_environment_is_restored(original_value):
    test_config = import_module("backend.tests.conftest")
    environment = {}
    if original_value is not None:
        environment["MI_AI_TEST_MODE"] = original_value

    original = test_config._activate_test_mode(environment)
    assert environment["MI_AI_TEST_MODE"] == "1"
    test_config._finish_test_session(environment, original, [])

    if original_value is None:
        assert "MI_AI_TEST_MODE" not in environment
    else:
        assert environment["MI_AI_TEST_MODE"] == original_value


def test_firebase_credential_helper_rejects_direct_test_mode_calls(monkeypatch):
    app_module = import_module("backend.app")
    reads = []

    def track_environment_read(*args, **kwargs):
        name = args[0] if args else None
        reads.append(name)
        return "1" if name == "MI_AI_TEST_MODE" else None

    def fail_if_credential_read(*args, **kwargs):
        raise AssertionError("Credential material was accessed in test mode.")

    monkeypatch.setattr(app_module, "MI_AI_TEST_MODE", False)
    with monkeypatch.context() as patch:
        patch.setattr(app_module.os, "getenv", track_environment_read)
        patch.setattr(app_module.os.path, "isfile", fail_if_credential_read)
        patch.setattr(
            app_module.firebase_admin_credentials,
            "Certificate",
            fail_if_credential_read,
        )
        with pytest.raises(
            RuntimeError,
            match="credential loading is disabled in test mode",
        ):
            app_module.mi_load_firebase_credential()

    assert reads == ["MI_AI_TEST_MODE"]


def test_backend_app_import_in_test_mode_never_initializes_firebase(monkeypatch):
    import firebase_admin
    import dotenv
    from firebase_admin import credentials, firestore

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Firebase SDK entry point was called in test mode.")

    dotenv_loader = dotenv.load_dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", fail_if_called)
    monkeypatch.setattr(firebase_admin, "initialize_app", fail_if_called)
    monkeypatch.setattr(firebase_admin, "get_app", fail_if_called)
    monkeypatch.setattr(credentials, "Certificate", fail_if_called)
    monkeypatch.setattr(firestore, "client", fail_if_called)

    app_module = import_module("backend.app")
    app_module.load_dotenv = dotenv_loader

    assert os.environ["MI_AI_TEST_MODE"] == "1"
    assert app_module.MI_FIREBASE_AUTH_READY is False
    assert app_module.MI_FIREBASE_DB is None
    assert app_module.MI_FIREBASE_AUTH_ERROR == (
        "Firebase Admin is disabled in test mode."
    )


def test_backend_app_reload_in_test_mode_never_initializes_firebase(monkeypatch):
    import firebase_admin
    import dotenv
    from firebase_admin import credentials, firestore

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Firebase SDK entry point was called in test mode.")

    dotenv_loader = dotenv.load_dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", fail_if_called)
    monkeypatch.setattr(firebase_admin, "initialize_app", fail_if_called)
    monkeypatch.setattr(firebase_admin, "get_app", fail_if_called)
    monkeypatch.setattr(credentials, "Certificate", fail_if_called)
    monkeypatch.setattr(firestore, "client", fail_if_called)

    app_module = reload(import_module("backend.app"))
    app_module.load_dotenv = dotenv_loader

    assert app_module.MI_FIREBASE_AUTH_READY is False
    assert app_module.MI_FIREBASE_DB is None


def test_direct_firestore_client_creation_is_blocked():
    from firebase_admin import firestore

    with pytest.raises(RuntimeError, match="client creation is disabled in tests"):
        firestore.client()


def test_chief_owner_database_access_cannot_bypass_test_mode():
    control_module = import_module("backend.chief_owner_control")
    rbac_module = import_module("backend.chief_owner_rbac")

    with pytest.raises(RuntimeError, match="disabled in test mode"):
        control_module.database()
    with pytest.raises(RuntimeError, match="disabled in test mode"):
        rbac_module.db()


def test_scoped_sdk_patches_are_restored(monkeypatch):
    from firebase_admin import firestore

    guarded_client = firestore.client
    replacement = lambda: None
    with monkeypatch.context() as patch:
        patch.setattr(firestore, "client", replacement)
        assert firestore.client is replacement

    assert firestore.client is guarded_client


def test_api_chat_route_returns_reply(monkeypatch):
    app_module = import_module("backend.app")

    class FakeResponse:
        text = "Hello from the test client"

    class FakeModels:
        def generate_content(self, **kwargs):
            return FakeResponse()

    class FakeClient:
        def __init__(self):
            self.models = FakeModels()

    monkeypatch.setattr(app_module, "get_groq_client", lambda: FakeClient())

    client = app_module.app.test_client()
    response = client.post("/api/chat", json={"message": "Hello"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["response"] == "Hello from the test client"
    assert payload["reply"] == "Hello from the test client"


def test_api_chat_route_supports_groq_style_client(monkeypatch):
    app_module = import_module("backend.app")

    class FakeMessage:
        content = "Hello from Groq"

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletionResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            return FakeCompletionResponse()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeGroqClient:
        def __init__(self):
            self.chat = FakeChat()

    monkeypatch.setattr(app_module, "get_groq_client", lambda: FakeGroqClient())

    client = app_module.app.test_client()
    response = client.post("/api/chat", json={"message": "Hello"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["response"] == "Hello from Groq"
    assert payload["reply"] == "Hello from Groq"


def test_api_chat_stream_route_emits_deltas(monkeypatch):
    app_module = import_module("backend.app")

    class FakeChunk:
        text = "Hello"

    class FakeStreamResponse:
        def __iter__(self):
            yield FakeChunk()
            yield FakeChunk()

    class FakeModels:
        def generate_content_stream(self, **kwargs):
            return FakeStreamResponse()

    class FakeClient:
        def __init__(self):
            self.models = FakeModels()

    monkeypatch.setattr(app_module, "get_groq_client", lambda: FakeClient())

    client = app_module.app.test_client()
    response = client.post("/api/chat/stream", json={"message": "Hello"})

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    lines = [line for line in body.splitlines() if line.strip()]
    assert any("delta" in line for line in lines)
    assert any("done" in line for line in lines)
    payloads = [json.loads(line.replace("data: ", "")) for line in lines if line.startswith("data:")]
    assert payloads[0]["type"] == "delta"
    assert payloads[-1]["type"] == "done"


def test_backend_dotenv_file_is_loaded_for_groq_settings(tmp_path, monkeypatch):
    app_module = import_module("backend.app")
    env_path = tmp_path / "test.env"
    env_path.write_text("GROQ_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    assert app_module.load_dotenv(str(env_path), override=False)
    assert app_module._get_groq_api_key() == "from-dotenv"


def test_generate_image_route_returns_generated_image(monkeypatch):
    app_module = import_module("backend.app")

    class FakeAsyncResponse:
        status_code = 202
        text = '{"id": "abc123"}'

    class FakeCheckResponse:
        status_code = 200
        text = '{"done": true, "finished": 1}'

    class FakeStatusResponse:
        status_code = 200
        text = '{"generations": [{"img": "dGVzdA=="}, {"image": "dGVzdA=="}]}'

    def fake_post(url, **kwargs):
        return FakeAsyncResponse()

    def fake_get(url, **kwargs):
        if url.endswith("/check/abc123"):
            return FakeCheckResponse()
        if url.endswith("/status/abc123"):
            return FakeStatusResponse()
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(app_module.requests, "post", fake_post)
    monkeypatch.setattr(app_module.requests, "get", fake_get)

    client = app_module.app.test_client()
    response = client.post("/api/generate-image", json={"prompt": "Give me a lion photo"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["prompt"] == "lion photo"
    assert payload["format"] == "webp"
    assert payload["image"].startswith("data:image/webp;base64,")


def test_assistant_info_route_returns_identity_and_contacts():
    app_module = import_module("backend.app")

    client = app_module.app.test_client()
    response = client.get("/api/assistant-info")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["name"] == "CORTEX CORE AI"
    assert payload["creator"] == "M.I. Muhammadh"
    assert payload["owner"] == "M.I. Muhammadh"
    assert payload["developer"] == "M.I. Muhammadh"
    assert payload["creator_age"] == 17
    assert payload["customer_support_email"] == "miai.customerservice@gmail.com"
    assert payload["other_requirements_email"] == "teamofchatbot.miai@gmail.com"
    assert payload["team_whatsapp_number"] == "+94756390621"


def _whatsapp_signature(app_secret, body):
    digest = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_whatsapp_webhook_verification_returns_challenge(monkeypatch):
    app_module = import_module("backend.app")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "test-verify-token")

    response = app_module.app.test_client().get(
        "/api/whatsapp/webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "test-verify-token",
            "hub.challenge": "challenge-123",
        },
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "challenge-123"


def test_whatsapp_webhook_rejects_invalid_verification_token(monkeypatch):
    app_module = import_module("backend.app")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "expected-token")

    response = app_module.app.test_client().get(
        "/api/whatsapp/webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "incorrect-token",
            "hub.challenge": "challenge-123",
        },
    )

    assert response.status_code == 403


def test_whatsapp_webhook_rejects_invalid_signature(monkeypatch):
    app_module = import_module("backend.app")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-access-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "15550000001")
    monkeypatch.setenv("WHATSAPP_GRAPH_API_VERSION", "v99.0")
    body = json.dumps({"object": "whatsapp_business_account"}).encode("utf-8")

    response = app_module.app.test_client().post(
        "/api/whatsapp/webhook",
        data=body,
        content_type="application/json",
        headers={"X-Hub-Signature-256": "sha256=invalid"},
    )

    assert response.status_code == 403


def test_whatsapp_webhook_generates_and_sends_ai_reply(monkeypatch, caplog):
    app_module = import_module("backend.app")
    app_secret = "test-app-secret"
    caplog.set_level("INFO", logger=app_module.app.logger.name)
    monkeypatch.setenv("WHATSAPP_APP_SECRET", app_secret)
    monkeypatch.setenv("WHATSAPP_ID_HMAC_KEY", "test-stable-id-hmac-key-0123456789")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-access-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "15550000001")
    monkeypatch.setenv("WHATSAPP_GRAPH_API_VERSION", "v99.0")
    monkeypatch.setitem(app_module.app.config, "WHATSAPP_AWAY_PHONE_NUMBER_ID", "")
    monkeypatch.setattr(app_module, "MI_FIREBASE_DB", _FakeFirestore())

    generated = []
    sent = []

    def fake_chat(payload):
        generated.append(payload)
        return app_module.jsonify({"reply": "Hello from CORTEX CORE AI"})

    monkeypatch.setattr(app_module, "_handle_chat_request", fake_chat)
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda phone_id, recipient, reply, **kwargs: sent.append((phone_id, recipient, reply)),
    )
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "15550000001"},
                    "messages": [{
                        "from": "15551234567",
                        "id": "wamid.test-message-id",
                        "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
                        "type": "text",
                        "text": {"body": "Hi there"},
                    }],
                },
            }],
        }],
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    response = app_module.app.test_client().post(
        "/api/whatsapp/webhook",
        data=body,
        content_type="application/json",
        headers={"X-Hub-Signature-256": _whatsapp_signature(app_secret, body)},
    )

    assert response.status_code == 200
    assert generated[0]["message"] == "Hi there"
    assert generated[0]["history"][0]["role"] == "system"
    assert "MI CORTEX X INC" in generated[0]["history"][0]["content"]
    assert len(generated[0]["history"]) == 1
    assert sent == [(
        "15550000001",
        "15551234567",
        "Hello from CORTEX CORE AI",
    )]
    assert "WHATSAPP_WEBHOOK_RECEIVED" in caplog.text
    assert "WHATSAPP_PAYLOAD_VALIDATED" in caplog.text
    assert "WHATSAPP_MESSAGE_EXTRACTED" in caplog.text
    assert "WHATSAPP_AI_REQUEST_STARTED" in caplog.text
    assert "WHATSAPP_AI_RESPONSE_RECEIVED" in caplog.text
    assert "WHATSAPP_SEND_REQUEST_STARTED" in caplog.text
    assert "WHATSAPP_MESSAGE_PROCESSING_COMPLETED" in caplog.text
    assert "WHATSAPP_WEBHOOK_COMPLETED" in caplog.text
    assert "Hi there" not in caplog.text
    assert "15551234567" not in caplog.text
    assert "test-access-token" not in caplog.text


def test_whatsapp_sender_uses_configured_cloud_api(monkeypatch, caplog):
    app_module = import_module("backend.app")
    caplog.set_level("INFO", logger=app_module.app.logger.name)
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-access-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "15550000001")
    monkeypatch.setenv("WHATSAPP_GRAPH_API_VERSION", "v99.0")
    calls = []

    class FakeResponse:
        status_code = 200

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(app_module.requests, "post", fake_post)
    app_module._send_whatsapp_text(
        "15550000001", "15551234567", "Test reply"
    )

    assert calls[0][0] == (
        "https://graph.facebook.com/v99.0/15550000001/messages"
    )
    assert calls[0][1]["headers"]["Authorization"] == "Bearer test-access-token"
    assert calls[0][1]["json"]["to"] == "15551234567"
    assert calls[0][1]["json"]["text"]["body"] == "Test reply"
    assert "WHATSAPP_SEND_SUCCESS" in caplog.text
    assert "test-access-token" not in caplog.text


def test_whatsapp_sender_logs_only_meta_error_code_on_rejection(monkeypatch, caplog):
    app_module = import_module("backend.app")
    caplog.set_level("WARNING", logger=app_module.app.logger.name)
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-access-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "15550000001")
    monkeypatch.setenv("WHATSAPP_GRAPH_API_VERSION", "v99.0")

    class FakeResponse:
        status_code = 400

        def json(self):
            return {
                "error": {
                    "code": 131026,
                    "message": "Sensitive provider diagnostic",
                }
            }

    monkeypatch.setattr(
        app_module.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(),
    )

    with pytest.raises(app_module._WhatsAppSendRejected):
        app_module._send_whatsapp_text(
            "15550000001",
            "15551234567",
            "Private reply",
            correlation_id="test-correlation",
        )

    assert "WHATSAPP_SEND_FAILED" in caplog.text
    assert "http_status=400" in caplog.text
    assert "meta_error_code=131026" in caplog.text
    assert "Sensitive provider diagnostic" not in caplog.text
    assert "15551234567" not in caplog.text
    assert "test-access-token" not in caplog.text


def test_whatsapp_webhook_logs_meta_delivery_status_without_recipient_data(
    monkeypatch,
    caplog,
):
    app_module = import_module("backend.app")
    phone_id = "15550000001"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    caplog.set_level("INFO", logger=app_module.app.logger.name)
    event = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": phone_id},
                    "messages": [],
                    "statuses": [{
                        "id": "wamid.private-status-id",
                        "status": "failed",
                        "recipient_id": "15551234567",
                        "errors": [{
                            "code": 131026,
                            "message": "Sensitive delivery explanation",
                        }],
                    }],
                },
            }],
        }],
    }

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 200
    assert "WHATSAPP_DELIVERY_STATUS" in caplog.text
    assert "status=failed" in caplog.text
    assert "meta_error_codes=131026" in caplog.text
    assert "15551234567" not in caplog.text
    assert "wamid.private-status-id" not in caplog.text
    assert "Sensitive delivery explanation" not in caplog.text
    assert "test-access-token" not in caplog.text


def _configure_whatsapp(monkeypatch, app_module, senders):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("WHATSAPP_ID_HMAC_KEY", "test-stable-id-hmac-key-0123456789")
    monkeypatch.setenv("WHATSAPP_SENDERS_JSON", json.dumps(senders))
    monkeypatch.setenv("WHATSAPP_GRAPH_API_VERSION", "v27.0")
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    monkeypatch.setattr(app_module, "MI_FIREBASE_DB", _FakeFirestore())


def _post_whatsapp_event(client, payload, app_secret="test-app-secret"):
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return client.post(
        "/api/whatsapp/webhook",
        data=body,
        content_type="application/json",
        headers={"X-Hub-Signature-256": _whatsapp_signature(app_secret, body)},
    )


def _whatsapp_text_event(phone_number_id, message_id, sender, text, sender_user_id=None):
    incoming = {
        "id": message_id,
        "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
        "type": "text",
        "text": {"body": text},
    }
    if sender:
        incoming["from"] = sender
    if sender_user_id:
        incoming["from_user_id"] = sender_user_id
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": phone_number_id},
                    "messages": [incoming],
                },
            }],
        }],
    }


def test_whatsapp_routes_three_numbers_with_their_own_tokens(monkeypatch):
    app_module = import_module("backend.app")
    phone_ids = ["15550000001", "15550000002", "15550000003"]
    tokens = ["test-token-one", "test-token-two", "test-token-three"]
    _configure_whatsapp(monkeypatch, app_module, dict(zip(phone_ids, tokens)))

    ai_requests = []
    graph_requests = []

    def fake_chat(payload):
        ai_requests.append(payload)
        return app_module.jsonify({"reply": f"AI reply {len(ai_requests)}"})

    class FakeResponse:
        status_code = 200

    def fake_post(url, **kwargs):
        graph_requests.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(app_module, "_handle_chat_request", fake_chat)
    monkeypatch.setattr(app_module.requests, "post", fake_post)
    client = app_module.app.test_client()

    for index, phone_id in enumerate(phone_ids):
        event = _whatsapp_text_event(
            phone_id,
            f"wamid.three-number-{index}",
            "15551112222" if index < 2 else None,
            f"Question {index + 1}",
            "BSUID-customer-three" if index == 2 else None,
        )
        response = _post_whatsapp_event(client, event)
        assert response.status_code == 200

    assert len(ai_requests) == 3
    assert [call[0] for call in graph_requests] == [
        f"https://graph.facebook.com/v27.0/{phone_id}/messages"
        for phone_id in phone_ids
    ]
    assert [call[1]["headers"]["Authorization"] for call in graph_requests] == [
        f"Bearer {token}" for token in tokens
    ]
    assert graph_requests[0][1]["json"]["to"] == "15551112222"
    assert graph_requests[1][1]["json"]["to"] == "15551112222"
    assert graph_requests[2][1]["json"]["recipient"] == "BSUID-customer-three"
    assert "to" not in graph_requests[2][1]["json"]
    assert all(
        request["history"][0]["role"] == "system"
        and "MI CORTEX X INC" in request["history"][0]["content"]
        for request in ai_requests
    )


def test_whatsapp_keeps_context_per_customer_and_supports_sinhala(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000011"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    ai_requests = []

    def fake_chat(payload):
        ai_requests.append(payload)
        return app_module.jsonify({"reply": f"reply-{len(ai_requests)}"})

    monkeypatch.setattr(app_module, "_handle_chat_request", fake_chat)
    monkeypatch.setattr(app_module, "_send_whatsapp_text", lambda *args, **kwargs: None)
    client = app_module.app.test_client()

    events = [
        _whatsapp_text_event(phone_id, "wamid.sinhala", "15552220001", "ආයුබෝවන්"),
        _whatsapp_text_event(
            phone_id,
            "wamid.mixed-language",
            "15552220001",
            "Tell me more about MI CORTEX X INC, සිංහලෙන් කියන්න",
        ),
        _whatsapp_text_event(phone_id, "wamid.english-followup", "15552220001", "What projects have you developed?"),
        _whatsapp_text_event(phone_id, "wamid.other-customer", "15552220002", "Hello"),
    ]
    for event in events:
        assert _post_whatsapp_event(client, event).status_code == 200

    assert ai_requests[0]["message"] == "ආයුබෝවන්"
    assert ai_requests[0]["history"][0]["role"] == "system"
    assert "AUTO-CARD-MARKING" in ai_requests[0]["history"][0]["content"]
    assert ai_requests[1]["message"] == (
        "Tell me more about MI CORTEX X INC, සිංහලෙන් කියන්න"
    )
    assert ai_requests[1]["history"][1:] == [
        {"role": "user", "content": "ආයුබෝවන්"},
        {"role": "assistant", "content": "reply-1"},
    ]
    assert ai_requests[2]["message"] == "What projects have you developed?"
    assert ai_requests[2]["history"][1:] == [
        {"role": "user", "content": "ආයුබෝවන්"},
        {"role": "assistant", "content": "reply-1"},
        {"role": "user", "content": "Tell me more about MI CORTEX X INC, සිංහලෙන් කියන්න"},
        {"role": "assistant", "content": "reply-2"},
    ]
    assert ai_requests[3]["message"] == "Hello"
    assert ai_requests[3]["history"][1:] == []


def test_whatsapp_history_survives_a_new_database_client(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000012"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    first_database = app_module.MI_FIREBASE_DB
    generated = []

    def fake_chat(payload):
        generated.append(payload)
        return app_module.jsonify({"reply": f"Reply {len(generated)}"})

    monkeypatch.setattr(app_module, "_handle_chat_request", fake_chat)
    monkeypatch.setattr(app_module, "_send_whatsapp_text", lambda *args, **kwargs: None)
    client = app_module.app.test_client()

    first_event = _whatsapp_text_event(
        phone_id, "wamid.restart-first", "15552220012", "Remember this question"
    )
    assert _post_whatsapp_event(client, first_event).status_code == 200

    monkeypatch.setattr(
        app_module,
        "MI_FIREBASE_DB",
        _FakeFirestore(store=first_database.store),
    )
    followup_event = _whatsapp_text_event(
        phone_id, "wamid.restart-followup", "15552220012", "What did I ask?"
    )
    assert _post_whatsapp_event(client, followup_event).status_code == 200

    assert generated[1]["history"][1:] == [
        {"role": "user", "content": "Remember this question"},
        {"role": "assistant", "content": "Reply 1"},
    ]
    stored_data = repr(first_database.store)
    assert "15552220012" not in stored_data
    assert "wamid.restart-first" not in stored_data


def test_whatsapp_history_is_not_sent_to_live_search(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000023"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    original_chat_handler = app_module._handle_chat_request
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: app_module.jsonify({"reply": "Private prior answer"}),
    )
    monkeypatch.setattr(app_module, "_send_whatsapp_text", lambda *args, **kwargs: None)
    client = app_module.app.test_client()
    first_event = _whatsapp_text_event(
        phone_id, "wamid.search-first", "15552220023", "Private prior question"
    )
    assert _post_whatsapp_event(client, first_event).status_code == 200

    search_contexts = []
    model_messages = []
    monkeypatch.setattr(app_module, "_handle_chat_request", original_chat_handler)
    monkeypatch.setattr(app_module, "_mi_question_requires_web", lambda _message: True)
    monkeypatch.setattr(
        app_module,
        "_mi_live_search",
        lambda _message, context: (
            search_contexts.append(context["history"])
            or ("Fresh evidence", [], "general")
        ),
    )
    monkeypatch.setattr(app_module, "memory_context_for_message", lambda _message: "")

    class FakeMessage:
        content = "Context-aware follow-up answer"

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletionResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            model_messages.append(kwargs["messages"])
            return FakeCompletionResponse()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeGroqClient:
        def __init__(self):
            self.chat = FakeChat()

    monkeypatch.setattr(app_module, "get_groq_client", lambda: FakeGroqClient())
    followup_event = _whatsapp_text_event(
        phone_id, "wamid.search-followup", "15552220023", "Can you explain more?"
    )

    assert _post_whatsapp_event(client, followup_event).status_code == 200
    assert search_contexts == [""]
    sent_to_model = str(model_messages[0])
    assert "Private prior question" in sent_to_model
    assert "Private prior answer" in sent_to_model


def test_whatsapp_history_isolated_by_sender_account(monkeypatch):
    app_module = import_module("backend.app")
    phone_ids = ["15550000013", "15550000014"]
    _configure_whatsapp(
        monkeypatch,
        app_module,
        {phone_id: "test-access-token" for phone_id in phone_ids},
    )
    generated = []

    def fake_chat(payload):
        generated.append(payload)
        return app_module.jsonify({"reply": f"Reply {len(generated)}"})

    monkeypatch.setattr(app_module, "_handle_chat_request", fake_chat)
    monkeypatch.setattr(app_module, "_send_whatsapp_text", lambda *args, **kwargs: None)
    client = app_module.app.test_client()

    events = [
        _whatsapp_text_event(phone_ids[0], "wamid.sender-one", "15552220013", "First account"),
        _whatsapp_text_event(phone_ids[1], "wamid.sender-two", "15552220013", "Second account"),
        _whatsapp_text_event(phone_ids[0], "wamid.sender-one-followup", "15552220013", "Follow up"),
    ]
    for event in events:
        assert _post_whatsapp_event(client, event).status_code == 200

    assert generated[2]["history"][1:] == [
        {"role": "user", "content": "First account"},
        {"role": "assistant", "content": "Reply 1"},
    ]
    conversation_documents = [
        value
        for (collection_name, _), value in app_module.MI_FIREBASE_DB.store.items()
        if collection_name == "whatsappConversationMemory"
    ]
    assert len(conversation_documents) == 2


def test_whatsapp_stores_out_of_order_events_chronologically(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000022"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    generated = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: (
            generated.append(payload)
            or app_module.jsonify({"reply": f"Reply {len(generated)}"})
        ),
    )
    monkeypatch.setattr(app_module, "_send_whatsapp_text", lambda *args, **kwargs: None)
    now = int(datetime.now(timezone.utc).timestamp())
    later_event = _whatsapp_text_event(
        phone_id, "wamid.chronology-later", "15552220022", "Later message"
    )
    earlier_event = _whatsapp_text_event(
        phone_id, "wamid.chronology-earlier", "15552220022", "Earlier message"
    )
    later_event["entry"][0]["changes"][0]["value"]["messages"][0]["timestamp"] = str(now)
    earlier_event["entry"][0]["changes"][0]["value"]["messages"][0]["timestamp"] = str(now - 10)

    client = app_module.app.test_client()
    assert _post_whatsapp_event(client, later_event).status_code == 200
    assert _post_whatsapp_event(client, earlier_event).status_code == 200

    assert generated[1]["history"][1:] == []
    conversation = next(
        value
        for (collection_name, _), value in app_module.MI_FIREBASE_DB.store.items()
        if collection_name == "whatsappConversationMemory"
    )
    assert [turn["content"] for turn in conversation["turns"]] == [
        "Earlier message",
        "Reply 2",
        "Later message",
        "Reply 1",
    ]


def test_whatsapp_history_limit_and_retention_are_enforced(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000016"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    monkeypatch.setenv("WHATSAPP_CONTEXT_LIMIT", "2")
    monkeypatch.setenv("WHATSAPP_HISTORY_RETENTION_DAYS", "1")
    generated = []

    def fake_chat(payload):
        generated.append(payload)
        return app_module.jsonify({"reply": f"Reply {len(generated)}"})

    monkeypatch.setattr(app_module, "_handle_chat_request", fake_chat)
    monkeypatch.setattr(app_module, "_send_whatsapp_text", lambda *args, **kwargs: None)
    client = app_module.app.test_client()
    for index in range(3):
        event = _whatsapp_text_event(
            phone_id,
            f"wamid.limit-{index}",
            "15552220016",
            f"Question {index}",
        )
        assert _post_whatsapp_event(client, event).status_code == 200

    assert generated[2]["history"][1:] == [
        {"role": "user", "content": "Question 1"},
        {"role": "assistant", "content": "Reply 2"},
    ]
    stored_conversation = next(
        value
        for (collection_name, _), value in app_module.MI_FIREBASE_DB.store.items()
        if collection_name == "whatsappConversationMemory"
    )
    assert len(stored_conversation["turns"]) == 2
    assert datetime.now(timezone.utc) < stored_conversation["expiresAt"] <= (
        datetime.now(timezone.utc) + timedelta(days=1)
    )


def test_whatsapp_expired_history_is_deleted_before_context_use(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000017"
    customer_id = "15552220017"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    database = app_module.MI_FIREBASE_DB
    conversation_id = app_module._whatsapp_hmac_identifier(
        "conversation",
        [phone_id, "phone", customer_id],
    )
    old_time = datetime.now(timezone.utc) - timedelta(days=31)
    database.collection("whatsappConversationMemory").document(conversation_id).set({
        "turns": [
            {
                "role": "user",
                "content": "Expired private question",
                "timestamp": int(old_time.timestamp()),
                "createdAt": old_time,
            },
            {
                "role": "assistant",
                "content": "Expired private answer",
                "timestamp": int(old_time.timestamp()),
                "createdAt": old_time,
            },
        ],
        "expiresAt": datetime.now(timezone.utc) - timedelta(seconds=1),
    })
    generated = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: (
            generated.append(payload)
            or app_module.jsonify({"reply": "Fresh answer"})
        ),
    )
    monkeypatch.setattr(app_module, "_send_whatsapp_text", lambda *args, **kwargs: None)
    event = _whatsapp_text_event(
        phone_id, "wamid.after-expiry", customer_id, "New question"
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 200
    assert generated[0]["history"][1:] == []
    stored_conversation = database.collection(
        "whatsappConversationMemory"
    ).document(conversation_id).get().to_dict()
    assert [turn["content"] for turn in stored_conversation["turns"]] == [
        "New question",
        "Fresh answer",
    ]
    assert "Expired private question" not in repr(database.store)


def test_whatsapp_storage_failure_does_not_fall_back_to_other_history(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000018"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    generated = []
    sent = []

    def fake_chat(payload):
        generated.append(payload)
        return app_module.jsonify({"reply": "Safe reply"})

    monkeypatch.setattr(app_module, "_handle_chat_request", fake_chat)
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda *args, **kwargs: sent.append(args),
    )
    client = app_module.app.test_client()
    first_event = _whatsapp_text_event(
        phone_id, "wamid.storage-first", "15552220018", "Private history"
    )
    assert _post_whatsapp_event(client, first_event).status_code == 200

    monkeypatch.setattr(app_module, "MI_FIREBASE_DB", None)
    second_event = _whatsapp_text_event(
        phone_id, "wamid.storage-failure", "15552220019", "Different customer"
    )
    response = _post_whatsapp_event(client, second_event)

    assert response.status_code == 502
    assert len(generated) == 1
    assert len(sent) == 1
    assert "Private history" not in response.get_data(as_text=True)


def test_whatsapp_failed_history_write_is_not_reported_as_success(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000020"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    database = _FailOnTransactionNumber(fail_on=3)
    monkeypatch.setattr(app_module, "MI_FIREBASE_DB", database)
    generated = []
    sent = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: (
            generated.append(payload)
            or app_module.jsonify({"reply": "Reply not yet persisted"})
        ),
    )
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda *args, **kwargs: sent.append(args),
    )
    event = _whatsapp_text_event(
        phone_id, "wamid.failed-write", "15552220020", "Persist this"
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 502
    assert len(generated) == 1
    assert len(sent) == 1
    conversation_documents = [
        value
        for (collection_name, _), value in database.store.items()
        if collection_name == "whatsappConversationMemory"
    ]
    assert len(conversation_documents) == 1
    assert conversation_documents[0]["turns"] == []
    assert "persisted" not in response.get_data(as_text=True).lower()


def test_whatsapp_same_customer_messages_are_serialized_across_requests(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000019"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    first_entered_ai = Event()
    release_first = Event()
    generated = []
    sent = []

    def fake_chat(payload):
        generated.append(payload)
        if payload["message"] == "First question":
            first_entered_ai.set()
            release_first.wait(timeout=3)
        return app_module.jsonify({"reply": f"Reply to {payload['message']}"})

    monkeypatch.setattr(app_module, "_handle_chat_request", fake_chat)
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda *args, **kwargs: sent.append(args),
    )
    first_event = _whatsapp_text_event(
        phone_id, "wamid.serial-first", "15552220019", "First question"
    )
    second_event = _whatsapp_text_event(
        phone_id, "wamid.serial-second", "15552220019", "Second question"
    )

    def deliver(event):
        with app_module.app.test_client() as client:
            return _post_whatsapp_event(client, event).status_code

    with ThreadPoolExecutor(max_workers=1) as executor:
        first_request = executor.submit(deliver, first_event)
        assert first_entered_ai.wait(timeout=3)
        assert deliver(second_event) == 503
        release_first.set()
        assert first_request.result(timeout=3) == 200

    assert deliver(second_event) == 200
    assert generated[1]["history"][1:] == [
        {"role": "user", "content": "First question"},
        {"role": "assistant", "content": "Reply to First question"},
    ]
    conversation_documents = [
        value
        for (collection_name, _), value in app_module.MI_FIREBASE_DB.store.items()
        if collection_name == "whatsappConversationMemory"
    ]
    assert len(conversation_documents) == 1
    assert len(conversation_documents[0]["turns"]) == 4
    assert len(sent) == 2


def test_whatsapp_processes_different_customers_concurrently(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000015"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    both_requests_reached_ai = Barrier(2)
    ai_requests = []
    result_lock = Lock()

    def fake_chat(payload):
        with result_lock:
            ai_requests.append(payload)
        both_requests_reached_ai.wait(timeout=3)
        return app_module.jsonify({"reply": "Concurrent reply"})

    monkeypatch.setattr(app_module, "_handle_chat_request", fake_chat)
    monkeypatch.setattr(app_module, "_send_whatsapp_text", lambda *args, **kwargs: None)
    events = [
        _whatsapp_text_event(phone_id, "wamid.concurrent-one", "15550001001", "First"),
        _whatsapp_text_event(phone_id, "wamid.concurrent-two", "15550001002", "Second"),
    ]

    def deliver(event):
        with app_module.app.test_client() as client:
            return _post_whatsapp_event(client, event).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(deliver, events))

    assert statuses == [200, 200]
    assert len(ai_requests) == 2
    assert all(len(item["history"]) == 1 for item in ai_requests)


def test_whatsapp_deduplicates_completed_webhook_delivery(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000021"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    database = app_module.MI_FIREBASE_DB
    ai_requests = []
    sent = []

    def fake_chat(payload):
        ai_requests.append(payload)
        return app_module.jsonify({"reply": "Only one reply"})

    monkeypatch.setattr(app_module, "_handle_chat_request", fake_chat)
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda *args, **kwargs: sent.append(args),
    )
    client = app_module.app.test_client()
    event = _whatsapp_text_event(
        phone_id, "wamid.duplicate", "15553330001", "Please reply once"
    )

    assert _post_whatsapp_event(client, event).status_code == 200
    assert _post_whatsapp_event(client, event).status_code == 200
    assert len(ai_requests) == 1
    assert len(sent) == 1
    conversation_documents = [
        value
        for (collection_name, _), value in database.store.items()
        if collection_name == "whatsappConversationMemory"
    ]
    assert len(conversation_documents) == 1
    assert len(conversation_documents[0]["turns"]) == 2
    receipts = [
        value
        for (collection_name, _), value in database.store.items()
        if collection_name == "whatsappMessageReceipts"
    ]
    assert len(receipts) == 1
    assert receipts[0]["status"] == "complete"


def test_whatsapp_retries_unknown_phone_number_id(monkeypatch, caplog):
    app_module = import_module("backend.app")
    caplog.set_level("WARNING", logger=app_module.app.logger.name)
    _configure_whatsapp(monkeypatch, app_module, {"15550000031": "approved-token"})
    ai_requests = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: ai_requests.append(payload),
    )
    event = _whatsapp_text_event(
        "15559999999", "wamid.unknown-sender", "15553330002", "Do not reply"
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 503
    assert ai_requests == []
    assert "reason=unconfigured_sender" in caplog.text
    assert "15559999999" not in caplog.text
    assert "15553330002" not in caplog.text
    assert "Do not reply" not in caplog.text
    assert "approved-token" not in caplog.text


def test_whatsapp_missing_sender_configuration_is_sanitized(monkeypatch):
    app_module = import_module("backend.app")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test-app-secret")
    monkeypatch.delenv("WHATSAPP_SENDERS_JSON", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("WHATSAPP_GRAPH_API_VERSION", "v27.0")
    event = _whatsapp_text_event(
        "15550000041", "wamid.missing-config", "15554440001", "Question"
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 503
    assert "test-app-secret" not in response.get_data(as_text=True)
    assert "test-access-token" not in response.get_data(as_text=True)


def test_whatsapp_message_outside_customer_service_window_is_ignored(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000046"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    event = _whatsapp_text_event(
        phone_id, "wamid.expired-window", "15554440006", "Old customer message"
    )
    event["entry"][0]["changes"][0]["value"]["messages"][0]["timestamp"] = str(
        int((datetime.now(timezone.utc) - timedelta(hours=24, seconds=1)).timestamp())
    )
    ai_requests = []
    sent = []
    claims = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: ai_requests.append(payload),
    )
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda *args, **kwargs: sent.append(args),
    )
    monkeypatch.setattr(
        app_module,
        "_whatsapp_claim_message",
        lambda *args, **kwargs: claims.append(args),
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
    assert ai_requests == []
    assert sent == []
    assert claims == []


def test_whatsapp_future_dated_message_is_ignored(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000048"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    event = _whatsapp_text_event(
        phone_id, "wamid.future-timestamp", "15554440008", "Future message"
    )
    event["entry"][0]["changes"][0]["value"]["messages"][0]["timestamp"] = str(
        int((datetime.now(timezone.utc) + timedelta(minutes=1)).timestamp())
    )
    ai_requests = []
    sent = []
    claims = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: ai_requests.append(payload),
    )
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda *args, **kwargs: sent.append(args),
    )
    monkeypatch.setattr(
        app_module,
        "_whatsapp_claim_message",
        lambda *args, **kwargs: claims.append(args),
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 200
    assert ai_requests == []
    assert sent == []
    assert claims == []


def test_whatsapp_message_without_timestamp_is_rejected(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000047"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    event = _whatsapp_text_event(
        phone_id, "wamid.missing-timestamp", "15554440007", "Question"
    )
    event["entry"][0]["changes"][0]["value"]["messages"][0].pop("timestamp")
    ai_requests = []
    sent = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: ai_requests.append(payload),
    )
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda *args, **kwargs: sent.append(args),
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 400
    assert ai_requests == []
    assert sent == []
    assert app_module.MI_FIREBASE_DB.store == {}


def test_whatsapp_ai_failure_is_retryable_and_does_not_send(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000051"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    sent = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: (app_module.jsonify({"error_code": "AI_SERVICE_UNAVAILABLE"}), 503),
    )
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda *args, **kwargs: sent.append(args),
    )
    event = _whatsapp_text_event(
        phone_id, "wamid.ai-failure", "15555550001", "Question"
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 503
    assert sent == []
    assert "AI_SERVICE_UNAVAILABLE" not in response.get_data(as_text=True)


def test_whatsapp_meta_failure_does_not_leak_secrets_or_message(monkeypatch, caplog):
    app_module = import_module("backend.app")
    phone_id = "15550000061"
    access_token = "sensitive-test-token"
    message = "private customer message"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: access_token})
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: app_module.jsonify({"reply": "private customer response"}),
    )

    class FailedMetaResponse:
        status_code = 401
        text = f"{access_token} must never be logged"

    monkeypatch.setattr(
        app_module.requests,
        "post",
        lambda *args, **kwargs: FailedMetaResponse(),
    )
    event = _whatsapp_text_event(
        phone_id, "wamid.graph-failure", "15556660001", message
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)
    response_text = response.get_data(as_text=True)

    assert response.status_code == 502
    assert access_token not in response_text
    assert message not in response_text
    assert access_token not in caplog.text
    assert message not in caplog.text


def test_whatsapp_meta_timeout_returns_sanitized_retryable_error(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000071"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: app_module.jsonify({"reply": "A reply"}),
    )

    def timeout(*args, **kwargs):
        raise app_module.requests.Timeout("test timeout")

    monkeypatch.setattr(app_module.requests, "post", timeout)
    event = _whatsapp_text_event(
        phone_id, "wamid.meta-timeout", "15557770001", "Question"
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 502
    assert "test timeout" not in response.get_data(as_text=True)


def test_whatsapp_empty_and_unsupported_messages_are_not_sent(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000081"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    ai_requests = []
    sent = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: ai_requests.append(payload),
    )
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda *args, **kwargs: sent.append(args),
    )
    empty_event = _whatsapp_text_event(
        phone_id, "wamid.empty", "15558880001", "   "
    )
    unsupported_event = _whatsapp_text_event(
        phone_id, "wamid.unsupported", "15558880001", "ignored"
    )
    unsupported_event["entry"][0]["changes"][0]["value"]["messages"][0]["type"] = "image"

    assert _post_whatsapp_event(app_module.app.test_client(), empty_event).status_code == 200
    assert _post_whatsapp_event(app_module.app.test_client(), unsupported_event).status_code == 200
    assert ai_requests == []
    assert sent == []


def test_whatsapp_rejects_malformed_entries(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000091"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    event = {"object": "whatsapp_business_account", "entry": {}}

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 400


def test_whatsapp_rejects_missing_or_invalid_customer_identity(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000092"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    generated = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: generated.append(payload),
    )
    missing_identity = _whatsapp_text_event(
        phone_id, "wamid.missing-customer", None, "Question"
    )
    invalid_identity = _whatsapp_text_event(
        phone_id, "wamid.invalid-customer", "not-a-phone-number", "Question"
    )

    responses = [
        _post_whatsapp_event(app_module.app.test_client(), missing_identity),
        _post_whatsapp_event(app_module.app.test_client(), invalid_identity),
    ]

    assert [response.status_code for response in responses] == [400, 400]
    assert generated == []
    assert not app_module.MI_FIREBASE_DB.store


class _FakeFirestoreSnapshot:
    def __init__(self, value):
        self.exists = value is not None
        self._value = value

    def to_dict(self):
        return dict(self._value or {})


class _FakeFirestoreDocument:
    def __init__(self, store, collection_name, document_id, on_write=None):
        self.store = store
        self.key = (collection_name, document_id)
        self.on_write = on_write

    def get(self, transaction=None):
        value = (
            transaction.read(self)
            if transaction is not None
            else self.store.get(self.key)
        )
        return _FakeFirestoreSnapshot(value)

    def set(self, value, merge=False):
        if merge:
            self.store[self.key] = {
                **self.store.get(self.key, {}),
                **value,
            }
        else:
            self.store[self.key] = dict(value)
        if self.on_write:
            self.on_write(self.key)


class _FakeFirestoreCollection:
    def __init__(self, store, collection_name, on_write=None):
        self.store = store
        self.collection_name = collection_name
        self.on_write = on_write

    def document(self, document_id):
        return _FakeFirestoreDocument(
            self.store,
            self.collection_name,
            document_id,
            self.on_write,
        )


class _FakeFirestoreTransaction:
    def __init__(self, store, versions=None):
        self.store = store
        self.versions = versions
        self.start_versions = dict(versions or {})
        self.snapshot = {
            key: dict(value)
            for key, value in store.items()
        }
        self.read_keys = set()
        self.writes = []

    def read(self, reference):
        self.read_keys.add(reference.key)
        value = self.snapshot.get(reference.key)
        return dict(value) if value is not None else None

    def set(self, reference, value, merge=False):
        self.writes.append((reference.key, dict(value), merge))

    def commit(self):
        for key, value, merge in self.writes:
            if merge:
                self.store[key] = {**self.store.get(key, {}), **value}
            else:
                self.store[key] = dict(value)
            if self.versions is not None:
                self.versions[key] = self.versions.get(key, 0) + 1

    def has_conflict(self):
        return self.versions is not None and any(
            self.versions.get(key, 0) != self.start_versions.get(key, 0)
            for key in self.read_keys
        )


class _FakeFirestore:
    def __init__(self, store=None):
        self.store = store if store is not None else {}
        self._transaction_lock = RLock()
        self._versions = {}
        self.transaction_attempts = 0
        self.transaction_attempt_hook = None
        self.committed_revisions = []

    def collection(self, collection_name):
        return _FakeFirestoreCollection(
            self.store,
            collection_name,
            self._record_write,
        )

    def _record_write(self, key):
        with self._transaction_lock:
            self._versions[key] = self._versions.get(key, 0) + 1

    def transaction(self):
        return _FakeFirestoreTransaction(self.store)

    def run_transaction(self, operation):
        for _ in range(5):
            with self._transaction_lock:
                self.transaction_attempts += 1
                transaction = _FakeFirestoreTransaction(
                    self.store,
                    self._versions,
                )
            result = operation(transaction)
            if self.transaction_attempt_hook:
                self.transaction_attempt_hook()
            with self._transaction_lock:
                if transaction.has_conflict():
                    continue
                transaction.commit()
                for key, value, _ in transaction.writes:
                    if "coexistenceEventVersion" in value:
                        self.committed_revisions.append(
                            self.store[key]["coexistenceEventVersion"]
                        )
                return result
        raise RuntimeError("Simulated Firestore transaction retry limit exceeded")


def _patch_fake_rbac_transaction(monkeypatch, rbac_module):
    def transactional(function):
        def apply(transaction):
            result = function(transaction)
            transaction.commit()
            return result
        return apply

    monkeypatch.setattr(
        rbac_module.firestore,
        "transactional",
        transactional,
    )


def _configure_rbac_owner(monkeypatch, rbac_module, database, uid_configured):
    monkeypatch.setattr(rbac_module, "CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(
        rbac_module,
        "CHIEF_OWNER_UID",
        "owner-uid" if uid_configured else "",
    )
    monkeypatch.setattr(
        rbac_module,
        "CHIEF_OWNER_UID_CONFIGURED",
        uid_configured,
    )
    monkeypatch.setattr(rbac_module, "CHIEF_OWNER_UID_CONFIG_VALID", True)
    monkeypatch.setattr(rbac_module, "db", lambda: database)
    _patch_fake_rbac_transaction(monkeypatch, rbac_module)


def test_rbac_bootstrap_requires_configured_uid_and_verified_email(monkeypatch):
    rbac_module = import_module("backend.chief_owner_rbac")
    database = _FakeFirestore()
    _configure_rbac_owner(monkeypatch, rbac_module, database, True)

    record = rbac_module._ensure_chief_owner({
        "uid": "owner-uid",
        "email": "owner@example.com",
        "email_verified": True,
    })

    owner_record = database.collection(
        "systemSettings"
    ).document("ownership").get().to_dict()
    assert owner_record["chiefOwnerUid"] == "owner-uid"
    assert record["role"] == "chief_owner"
    assert database.collection(
        "staffAccounts"
    ).document("owner-uid").get().to_dict()["email"] == "owner@example.com"


def test_rbac_accepts_only_matching_persisted_uid_without_uid_config(monkeypatch):
    rbac_module = import_module("backend.chief_owner_rbac")
    database = _FakeFirestore({
        ("systemSettings", "ownership"): {
            "chiefOwnerUid": "owner-uid",
            "chiefOwnerEmail": "owner@example.com",
        },
    })
    _configure_rbac_owner(monkeypatch, rbac_module, database, False)
    original_owner_record = dict(
        database.store[("systemSettings", "ownership")]
    )

    rbac_module._ensure_chief_owner({
        "uid": "owner-uid",
        "email": "owner@example.com",
        "email_verified": True,
    })
    assert database.store[("systemSettings", "ownership")] == (
        original_owner_record
    )

    with pytest.raises(
        rbac_module.AuthorizationError,
        match="different protected Chief Owner UID",
    ):
        rbac_module._ensure_chief_owner({
            "uid": "other-uid",
            "email": "owner@example.com",
            "email_verified": True,
        })


def test_rbac_does_not_bootstrap_without_uid_configuration(monkeypatch):
    rbac_module = import_module("backend.chief_owner_rbac")
    database = _FakeFirestore()
    _configure_rbac_owner(monkeypatch, rbac_module, database, False)

    with pytest.raises(rbac_module.AuthorizationError, match="UID is required"):
        rbac_module._ensure_chief_owner({
            "uid": "owner-uid",
            "email": "owner@example.com",
            "email_verified": True,
        })

    assert database.store == {}


def test_rbac_rejects_unverified_bootstrap_and_mismatched_staff_record(monkeypatch):
    rbac_module = import_module("backend.chief_owner_rbac")
    unverified_database = _FakeFirestore()
    _configure_rbac_owner(
        monkeypatch,
        rbac_module,
        unverified_database,
        True,
    )
    with pytest.raises(rbac_module.AuthorizationError, match="identity mismatch"):
        rbac_module._ensure_chief_owner({
            "uid": "owner-uid",
            "email": "owner@example.com",
            "email_verified": False,
        })
    assert unverified_database.store == {}

    mismatched_staff_database = _FakeFirestore({
        ("systemSettings", "ownership"): {
            "chiefOwnerUid": "owner-uid",
            "chiefOwnerEmail": "owner@example.com",
        },
        ("staffAccounts", "owner-uid"): {
            "uid": "owner-uid",
            "email": "admin@example.com",
            "role": "admin",
        },
    })
    _configure_rbac_owner(
        monkeypatch,
        rbac_module,
        mismatched_staff_database,
        True,
    )
    with pytest.raises(
        rbac_module.AuthorizationError,
        match="staff identity mismatch",
    ):
        rbac_module._ensure_chief_owner({
            "uid": "owner-uid",
            "email": "owner@example.com",
            "email_verified": True,
        })
    assert mismatched_staff_database.store[
        ("staffAccounts", "owner-uid")
    ]["email"] == "admin@example.com"


@pytest.mark.parametrize(
    "owner_record",
    [
        {"chiefOwnerUid": "different-uid", "chiefOwnerEmail": "owner@example.com"},
        {"chiefOwnerUid": "owner-uid", "chiefOwnerEmail": "admin@example.com"},
        {"chiefOwnerUid": "owner-uid", "chiefOwnerEmail": ""},
        {"chiefOwnerEmail": "owner@example.com"},
        {"chiefOwnerUid": ""},
    ],
)
def test_rbac_rejects_malformed_existing_owner_record_without_rewriting(
    monkeypatch,
    owner_record,
):
    rbac_module = import_module("backend.chief_owner_rbac")
    database = _FakeFirestore({
        ("systemSettings", "ownership"): dict(owner_record),
    })
    original = dict(database.store[("systemSettings", "ownership")])
    _configure_rbac_owner(monkeypatch, rbac_module, database, True)

    with pytest.raises(rbac_module.AuthorizationError):
        rbac_module._ensure_chief_owner({
            "uid": "owner-uid",
            "email": "owner@example.com",
            "email_verified": True,
        })

    assert database.store[("systemSettings", "ownership")] == original


def test_rbac_preserves_legacy_uid_only_owner_record(monkeypatch):
    rbac_module = import_module("backend.chief_owner_rbac")
    database = _FakeFirestore({
        ("systemSettings", "ownership"): {
            "chiefOwnerUid": "owner-uid",
            "legacyField": "preserve",
        },
    })
    original = dict(database.store[("systemSettings", "ownership")])
    _configure_rbac_owner(monkeypatch, rbac_module, database, True)

    rbac_module._ensure_chief_owner({
        "uid": "owner-uid",
        "email": "owner@example.com",
        "email_verified": True,
    })

    assert database.store[("systemSettings", "ownership")] == original


def test_rbac_fails_closed_when_persisted_owner_record_cannot_be_read(
    monkeypatch,
):
    rbac_module = import_module("backend.chief_owner_rbac")
    app_module = import_module("backend.app")

    class FailingDocument:
        def get(self, transaction=None):
            raise RuntimeError("simulated Firestore read failure")

    class FailingCollection:
        def document(self, document_id):
            return FailingDocument()

    class FailingDatabase:
        def collection(self, collection_name):
            return FailingCollection()

        def transaction(self):
            return _FakeFirestoreTransaction({})

    monkeypatch.setattr(rbac_module, "CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(rbac_module, "CHIEF_OWNER_UID", "owner-uid")
    monkeypatch.setattr(rbac_module, "CHIEF_OWNER_UID_CONFIGURED", True)
    monkeypatch.setattr(rbac_module, "CHIEF_OWNER_UID_CONFIG_VALID", True)
    monkeypatch.setattr(rbac_module, "_firebase_ready", lambda: None)
    monkeypatch.setattr(
        rbac_module,
        "auth",
        SimpleNamespace(
            verify_id_token=lambda *args, **kwargs: {
                "uid": "owner-uid",
                "email": "owner@example.com",
                "email_verified": True,
            }
        ),
    )
    monkeypatch.setattr(rbac_module, "db", FailingDatabase)
    _patch_fake_rbac_transaction(monkeypatch, rbac_module)

    response = app_module.app.test_client().get(
        "/api/rbac/me",
        headers={"Authorization": "Bearer test-id-token"},
    )

    assert response.status_code == 500
    assert response.get_json()["error"] == "authorization_failed"


@pytest.mark.parametrize(
    ("persisted_uid", "uid_configured", "uid_config_valid", "expected_status"),
    [
        ("owner-uid", False, True, 200),
        ("different-uid", False, True, 403),
        (None, False, True, 403),
        ("owner-uid", True, False, 403),
    ],
)
def test_chief_owner_control_requires_verified_persisted_identity(
    monkeypatch,
    persisted_uid,
    uid_configured,
    uid_config_valid,
    expected_status,
):
    app_module = import_module("backend.app")
    control_module = import_module("backend.chief_owner_control")
    store = {}
    if persisted_uid is not None:
        store[("systemSettings", "ownership")] = {
            "chiefOwnerUid": persisted_uid,
            "chiefOwnerEmail": "owner@example.com",
        }
    database = _FakeFirestore(store)
    monkeypatch.setattr(control_module, "CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(
        control_module,
        "CHIEF_OWNER_UID",
        "owner-uid" if uid_configured and uid_config_valid else "",
    )
    monkeypatch.setattr(
        control_module,
        "CHIEF_OWNER_UID_CONFIGURED",
        uid_configured,
    )
    monkeypatch.setattr(
        control_module,
        "CHIEF_OWNER_UID_CONFIG_VALID",
        uid_config_valid,
    )
    monkeypatch.setattr(
        control_module,
        "firebase_auth",
        SimpleNamespace(
            verify_id_token=lambda *args, **kwargs: {
                "uid": "owner-uid",
                "email": "owner@example.com",
                "email_verified": True,
            }
        ),
    )
    monkeypatch.setattr(control_module, "database", lambda: database)
    monkeypatch.setattr(
        control_module,
        "persisted_chief_owner_uid",
        lambda: app_module.read_persisted_chief_owner_uid(
            database,
            configured_email=control_module.CHIEF_OWNER_EMAIL,
        ),
    )

    response = app_module.app.test_client().get(
        "/api/chief-owner/options",
        headers={"Authorization": "Bearer test-id-token"},
    )

    assert response.status_code == expected_status
    if expected_status == 403:
        assert database.store == store


@pytest.mark.parametrize(
    ("uid", "expected_owner"),
    [
        ("owner-uid", True),
        ("other-uid", False),
        ("", False),
    ],
)
def test_legacy_and_admin_owner_status_use_persisted_uid(
    monkeypatch,
    uid,
    expected_owner,
):
    app_module = import_module("backend.app")
    database = _FakeFirestore({
        ("systemSettings", "ownership"): {
            "chiefOwnerUid": "owner-uid",
            "chiefOwnerEmail": "owner@example.com",
        },
    })
    monkeypatch.setattr(app_module, "CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(app_module, "MI_CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(app_module, "MI_AI_CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(app_module, "CHIEF_OWNER_UID", "")
    monkeypatch.setattr(app_module, "MI_AI_CHIEF_OWNER_UID", "")
    monkeypatch.setattr(app_module, "CHIEF_OWNER_UID_CONFIGURED", False)
    monkeypatch.setattr(app_module, "CHIEF_OWNER_UID_CONFIG_VALID", True)
    monkeypatch.setattr(app_module, "_firestore_database", lambda: database)

    decoded = {
        "uid": uid,
        "email": "owner@example.com",
        "email_verified": True,
    }
    monkeypatch.setattr(
        app_module,
        "_mi_owner_verify_token",
        lambda: (decoded, None),
    )
    monkeypatch.setattr(
        app_module,
        "mi_ai_verify_firebase_token",
        lambda: (decoded, None),
    )
    client = app_module.app.test_client()

    legacy = client.get(
        "/api/chief-owner/me",
        headers={"Authorization": "Bearer test-id-token"},
    ).get_json()
    admin = client.get(
        "/api/admin/me",
        headers={"Authorization": "Bearer test-id-token"},
    ).get_json()

    assert legacy["isChiefOwner"] is expected_owner
    assert admin["isChiefOwner"] is expected_owner


@pytest.mark.parametrize(
    ("owner_record", "expected_status", "expected_owner"),
    [
        (
            {
                "chiefOwnerUid": "owner-uid",
                "chiefOwnerEmail": "owner@example.com",
            },
            200,
            True,
        ),
        ({"chiefOwnerUid": "owner-uid"}, 200, True),
        (
            {
                "chiefOwnerUid": "different-uid",
                "chiefOwnerEmail": "owner@example.com",
            },
            200,
            False,
        ),
        (
            {
                "chiefOwnerUid": "owner-uid",
                "chiefOwnerEmail": "admin@example.com",
            },
            503,
            False,
        ),
        (
            {"chiefOwnerUid": "owner-uid", "chiefOwnerEmail": ""},
            503,
            False,
        ),
        ({"chiefOwnerEmail": "owner@example.com"}, 503, False),
        ({"chiefOwnerUid": ""}, 503, False),
        ({}, 503, False),
        (None, 200, True),
    ],
)
def test_legacy_and_modern_status_share_persisted_owner_validation(
    monkeypatch,
    owner_record,
    expected_status,
    expected_owner,
):
    app_module = import_module("backend.app")
    store = {}
    if owner_record is not None:
        store[("systemSettings", "ownership")] = owner_record
    database = _FakeFirestore(store)
    monkeypatch.setattr(app_module, "CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(app_module, "MI_CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(
        app_module,
        "MI_AI_CHIEF_OWNER_EMAIL",
        "owner@example.com",
    )
    monkeypatch.setattr(app_module, "CHIEF_OWNER_UID", "owner-uid")
    monkeypatch.setattr(app_module, "MI_AI_CHIEF_OWNER_UID", "owner-uid")
    monkeypatch.setattr(app_module, "CHIEF_OWNER_UID_CONFIGURED", True)
    monkeypatch.setattr(app_module, "CHIEF_OWNER_UID_CONFIG_VALID", True)
    monkeypatch.setattr(app_module, "_firestore_database", lambda: database)
    decoded = {
        "uid": "owner-uid",
        "email": "owner@example.com",
        "email_verified": True,
    }
    monkeypatch.setattr(
        app_module,
        "_mi_owner_verify_token",
        lambda: (decoded, None),
    )
    monkeypatch.setattr(
        app_module,
        "mi_ai_verify_firebase_token",
        lambda: (decoded, None),
    )
    client = app_module.app.test_client()

    headers = {"Authorization": "Bearer test-id-token"}
    legacy = client.get("/api/chief-owner/me", headers=headers)
    admin = client.get("/api/admin/me", headers=headers)
    permission = client.post(
        "/api/admin/permission-check",
        headers=headers,
        json={"permission": "users.view"},
    )

    assert [legacy.status_code, admin.status_code] == [
        expected_status,
        expected_status,
    ]
    assert legacy.get_json()["isChiefOwner"] is expected_owner
    assert admin.get_json()["isChiefOwner"] is expected_owner
    expected_permission_status = (
        503 if expected_status == 503 else 200 if expected_owner else 403
    )
    assert permission.status_code == expected_permission_status
    assert permission.get_json()["allowed"] is expected_owner


@pytest.mark.parametrize(
    ("scenario", "expected_status", "expected_owner"),
    [
        ("valid-owner", 200, True),
        ("revoked-owner", 401, False),
        ("invalid-token", 401, False),
        ("missing-token", 401, False),
        ("ordinary-admin", 200, False),
    ],
)
def test_legacy_owner_status_checks_revocation_and_identity(
    monkeypatch,
    scenario,
    expected_status,
    expected_owner,
):
    import firebase_admin.auth as firebase_auth

    app_module = import_module("backend.app")
    database = _FakeFirestore({
        ("systemSettings", "ownership"): {
            "chiefOwnerUid": "owner-uid",
            "chiefOwnerEmail": "owner@example.com",
        },
    })
    monkeypatch.setattr(app_module, "CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(app_module, "MI_CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(app_module, "CHIEF_OWNER_UID", "owner-uid")
    monkeypatch.setattr(app_module, "CHIEF_OWNER_UID_CONFIGURED", True)
    monkeypatch.setattr(app_module, "CHIEF_OWNER_UID_CONFIG_VALID", True)
    monkeypatch.setattr(app_module, "_firestore_database", lambda: database)

    calls = []

    def verify_id_token(token, check_revoked=False):
        calls.append((token, check_revoked))
        if token in {"revoked", "invalid"}:
            raise ValueError("Token verification failed.")
        if token == "admin":
            return {
                "uid": "admin-uid",
                "email": "admin@example.com",
                "email_verified": True,
            }
        return {
            "uid": "owner-uid",
            "email": "owner@example.com",
            "email_verified": True,
        }

    monkeypatch.setattr(firebase_auth, "verify_id_token", verify_id_token)
    headers = (
        {}
        if scenario == "missing-token"
        else {
            "Authorization": "Bearer " + {
                "valid-owner": "valid",
                "revoked-owner": "revoked",
                "invalid-token": "invalid",
                "ordinary-admin": "admin",
                "missing-token": "",
            }[scenario]
        }
    )

    response = app_module.app.test_client().get(
        "/api/chief-owner/me",
        headers=headers,
    )
    payload = response.get_json()

    assert response.status_code == expected_status
    assert payload["isChiefOwner"] is expected_owner
    if scenario == "missing-token":
        assert calls == []
    else:
        assert calls == [(
            headers["Authorization"].split(" ", 1)[1],
            True,
        )]


def test_owner_status_fails_closed_when_persisted_record_cannot_be_read(
    monkeypatch,
):
    app_module = import_module("backend.app")
    monkeypatch.setattr(app_module, "CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(app_module, "MI_CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(
        app_module,
        "MI_AI_CHIEF_OWNER_EMAIL",
        "owner@example.com",
    )
    monkeypatch.setattr(app_module, "CHIEF_OWNER_UID", "owner-uid")
    monkeypatch.setattr(app_module, "MI_AI_CHIEF_OWNER_UID", "owner-uid")
    monkeypatch.setattr(app_module, "CHIEF_OWNER_UID_CONFIGURED", True)
    monkeypatch.setattr(app_module, "CHIEF_OWNER_UID_CONFIG_VALID", True)
    identity = {
        "uid": "owner-uid",
        "email": "owner@example.com",
        "email_verified": True,
    }
    monkeypatch.setattr(app_module, "_mi_owner_verify_token", lambda: (identity, None))
    monkeypatch.setattr(app_module, "mi_ai_verify_firebase_token", lambda: (identity, None))

    def fail_read():
        raise RuntimeError("simulated Firestore read failure")

    monkeypatch.setattr(app_module, "_firestore_database", fail_read)
    client = app_module.app.test_client()
    legacy = client.get(
        "/api/chief-owner/me",
        headers={"Authorization": "Bearer test-id-token"},
    )
    modern = client.get(
        "/api/admin/me",
        headers={"Authorization": "Bearer test-id-token"},
    )

    assert legacy.status_code == 503
    assert legacy.get_json()["isChiefOwner"] is False
    assert modern.status_code == 503
    assert modern.get_json()["isChiefOwner"] is False


@pytest.mark.parametrize(
    ("owner_record", "expected_status"),
    [
        (
            {
                "chiefOwnerUid": "owner-uid",
                "chiefOwnerEmail": "owner@example.com",
            },
            200,
        ),
        ({"chiefOwnerUid": "owner-uid"}, 200),
        (
            {
                "chiefOwnerUid": "owner-uid",
                "chiefOwnerEmail": "admin@example.com",
            },
            503,
        ),
        ({"chiefOwnerUid": "different-uid"}, 403),
        ({"chiefOwnerUid": ""}, 503),
    ],
)
def test_chief_owner_control_uses_shared_persisted_record_policy(
    monkeypatch,
    owner_record,
    expected_status,
):
    app_module = import_module("backend.app")
    control_module = import_module("backend.chief_owner_control")
    database = _FakeFirestore({
        ("systemSettings", "ownership"): owner_record,
    })
    monkeypatch.setattr(control_module, "CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(control_module, "CHIEF_OWNER_UID", "owner-uid")
    monkeypatch.setattr(control_module, "CHIEF_OWNER_UID_CONFIGURED", True)
    monkeypatch.setattr(control_module, "CHIEF_OWNER_UID_CONFIG_VALID", True)
    monkeypatch.setattr(
        control_module,
        "firebase_auth",
        SimpleNamespace(
            verify_id_token=lambda *args, **kwargs: {
                "uid": "owner-uid",
                "email": "owner@example.com",
                "email_verified": True,
            }
        ),
    )
    monkeypatch.setattr(control_module, "database", lambda: database)

    response = app_module.app.test_client().get(
        "/api/chief-owner/options",
        headers={"Authorization": "Bearer test-id-token"},
    )

    assert response.status_code == expected_status


def test_chief_owner_control_fails_closed_when_persisted_record_read_fails(
    monkeypatch,
):
    app_module = import_module("backend.app")
    control_module = import_module("backend.chief_owner_control")
    monkeypatch.setattr(control_module, "CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(control_module, "CHIEF_OWNER_UID", "owner-uid")
    monkeypatch.setattr(control_module, "CHIEF_OWNER_UID_CONFIGURED", True)
    monkeypatch.setattr(control_module, "CHIEF_OWNER_UID_CONFIG_VALID", True)
    monkeypatch.setattr(
        control_module,
        "firebase_auth",
        SimpleNamespace(
            verify_id_token=lambda *args, **kwargs: {
                "uid": "owner-uid",
                "email": "owner@example.com",
                "email_verified": True,
            }
        ),
    )

    def fail_read():
        raise RuntimeError("simulated Firestore read failure")

    monkeypatch.setattr(control_module, "database", fail_read)
    response = app_module.app.test_client().get(
        "/api/chief-owner/options",
        headers={"Authorization": "Bearer test-id-token"},
    )

    assert response.status_code == 503


@pytest.mark.parametrize("iteration", [1, 2])
def test_fake_firestore_fixture_has_isolated_state(fake_firestore, iteration):
    assert fake_firestore.store == {}
    fake_firestore.collection("test").document(str(iteration)).set({"value": iteration})
    assert len(fake_firestore.store) == 1


class _FailOnTransactionNumber(_FakeFirestore):
    def __init__(self, fail_on):
        super().__init__()
        self.fail_on = fail_on
        self.transaction_count = 0

    def run_transaction(self, operation):
        with self._transaction_lock:
            self.transaction_count += 1
            transaction = _FakeFirestoreTransaction(self.store)
            result = operation(transaction)
            if self.transaction_count == self.fail_on:
                raise RuntimeError("simulated Firestore transaction failure")
            transaction.commit()
            return result


def _configure_manual_away_mode(monkeypatch, app_module, phone_id, db, senders=None):
    configured_senders = senders or {phone_id: "test-away-token"}
    _configure_whatsapp(monkeypatch, app_module, configured_senders)
    monkeypatch.setitem(
        app_module.app.config,
        "WHATSAPP_AWAY_PHONE_NUMBER_ID",
        phone_id,
    )
    monkeypatch.setattr(app_module, "MI_FIREBASE_DB", db)


def _authorize_test_chief_owner(monkeypatch, app_module, email="owner@example.com"):
    control_module = import_module("backend.chief_owner_control")
    monkeypatch.setattr(control_module, "CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(control_module, "CHIEF_OWNER_UID", "owner-uid")

    class FakeFirebaseAuth:
        def verify_id_token(self, token, check_revoked=False):
            return {
                "uid": "owner-uid",
                "email": email,
                "email_verified": True,
            }

    monkeypatch.setattr(control_module, "CHIEF_OWNER_UID_CONFIGURED", True)
    monkeypatch.setattr(control_module, "CHIEF_OWNER_UID_CONFIG_VALID", True)
    monkeypatch.setattr(control_module, "firebase_auth", FakeFirebaseAuth())
    monkeypatch.setattr(control_module, "database", lambda: app_module.MI_FIREBASE_DB)
    monkeypatch.setattr(control_module, "persisted_chief_owner_uid", lambda: None)
    monkeypatch.setattr(control_module, "create_security_alert", lambda *args: None)
    return control_module, {"Authorization": "Bearer test-firebase-id-token"}


def test_whatsapp_available_suppresses_target_and_preserves_other_senders(monkeypatch):
    app_module = import_module("backend.app")
    target_phone_id = "15550000101"
    other_phone_ids = ["15550000102", "15550000103"]
    db = _FakeFirestore()
    db.collection("whatsappManualAvailability").document(target_phone_id).set({
        "phoneNumberId": target_phone_id,
        "mode": "AVAILABLE",
    })
    _configure_manual_away_mode(
        monkeypatch,
        app_module,
        target_phone_id,
        db,
        {
            target_phone_id: "target-test-token",
            other_phone_ids[0]: "other-test-token-one",
            other_phone_ids[1]: "other-test-token-two",
        },
    )
    ai_requests = []
    sent_from = []

    def fake_chat(payload):
        ai_requests.append(payload)
        return app_module.jsonify({"reply": "AI reply"})

    monkeypatch.setattr(app_module, "_handle_chat_request", fake_chat)
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda phone_id, *args, **kwargs: sent_from.append(phone_id),
    )
    client = app_module.app.test_client()
    target_event = _whatsapp_text_event(
        target_phone_id, "wamid.available-target", "15551110001", "Target question"
    )

    assert _post_whatsapp_event(client, target_event).status_code == 200
    assert not any(
        collection_name == "whatsappConversationMemory"
        for collection_name, _ in db.store
    )
    ignored_receipts = [
        value
        for (collection_name, _), value in db.store.items()
        if collection_name == "whatsappMessageReceipts"
    ]
    assert len(ignored_receipts) == 1
    assert ignored_receipts[0]["status"] == "ignored_available"
    assert "Target question" not in repr(ignored_receipts[0])

    db.collection("whatsappManualAvailability").document(target_phone_id).set({
        "phoneNumberId": target_phone_id,
        "mode": "AWAY",
    })
    assert _post_whatsapp_event(client, target_event).status_code == 200
    for index, other_phone_id in enumerate(other_phone_ids):
        other_event = _whatsapp_text_event(
            other_phone_id,
            f"wamid.other-sender-{index}",
            f"155511100{index + 2:02d}",
            f"Other question {index + 1}",
        )
        assert _post_whatsapp_event(client, other_event).status_code == 200

    assert [item["message"] for item in ai_requests] == [
        "Other question 1",
        "Other question 2",
    ]
    assert sent_from == other_phone_ids


def test_whatsapp_away_mode_allows_target_reply_from_target_sender(monkeypatch):
    app_module = import_module("backend.app")
    target_phone_id = "15550000111"
    db = _FakeFirestore()
    db.collection("whatsappManualAvailability").document(target_phone_id).set({
        "phoneNumberId": target_phone_id,
        "mode": "AWAY",
    })
    _configure_manual_away_mode(monkeypatch, app_module, target_phone_id, db)
    generated = []
    sent = []

    def fake_chat(payload):
        generated.append(payload)
        return app_module.jsonify({"reply": "Contextual AI reply"})

    monkeypatch.setattr(app_module, "_handle_chat_request", fake_chat)
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda phone_id, recipient, reply, **kwargs: sent.append(
            (phone_id, recipient, reply)
        ),
    )
    event = _whatsapp_text_event(
        target_phone_id, "wamid.away-target", "15552220001", "What projects?"
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 200
    assert generated[0]["message"] == "What projects?"
    followup = _whatsapp_text_event(
        target_phone_id,
        "wamid.away-target-followup",
        "15552220001",
        "Can you elaborate?",
    )
    assert _post_whatsapp_event(app_module.app.test_client(), followup).status_code == 200
    assert generated[1]["history"][1:] == [
        {"role": "user", "content": "What projects?"},
        {"role": "assistant", "content": "Contextual AI reply"},
    ]
    assert sent == [(
        target_phone_id,
        "15552220001",
        "Contextual AI reply",
    ), (
        target_phone_id,
        "15552220001",
        "Contextual AI reply",
    )]


def test_whatsapp_missing_or_unavailable_mode_fails_closed(monkeypatch):
    app_module = import_module("backend.app")
    control_module = import_module("backend.chief_owner_control")
    target_phone_id = "15550000121"
    db = _FakeFirestore()
    _configure_manual_away_mode(monkeypatch, app_module, target_phone_id, db)
    control_module, headers = _authorize_test_chief_owner(
        monkeypatch, app_module
    )
    client = app_module.app.test_client()

    default_response = client.get(
        "/api/chief-owner/whatsapp-away-mode",
        headers=headers,
    )
    assert default_response.status_code == 200
    assert default_response.get_json()["mode"] == "AVAILABLE"
    assert default_response.get_json()["stateSource"] == "default"

    monkeypatch.setattr(app_module, "MI_FIREBASE_DB", None)
    unavailable_response = client.get(
        "/api/chief-owner/whatsapp-away-mode",
        headers=headers,
    )
    assert unavailable_response.status_code == 200
    assert unavailable_response.get_json()["mode"] == "AVAILABLE"
    assert unavailable_response.get_json()["stateSource"] == "unavailable"

    generated = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: generated.append(payload),
    )
    event = _whatsapp_text_event(
        target_phone_id, "wamid.unavailable-mode", "15553330001", "Do not reply"
    )
    response = _post_whatsapp_event(client, event)
    assert response.status_code == 502
    assert generated == []


def test_chief_owner_can_switch_whatsapp_mode_without_restart(monkeypatch):
    app_module = import_module("backend.app")
    target_phone_id = "15550000131"
    db = _FakeFirestore()
    _configure_manual_away_mode(monkeypatch, app_module, target_phone_id, db)
    _, headers = _authorize_test_chief_owner(monkeypatch, app_module)
    client = app_module.app.test_client()
    generated = []
    sent = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: (
            generated.append(payload)
            or app_module.jsonify({"reply": "Manual away reply"})
        ),
    )
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda phone_id, recipient, reply, **kwargs: sent.append(phone_id),
    )

    update = client.post(
        "/api/chief-owner/whatsapp-away-mode",
        json={"mode": "AWAY"},
        headers=headers,
    )

    assert update.status_code == 200
    assert update.get_json()["mode"] == "AWAY"
    assert app_module._whatsapp_manual_mode(target_phone_id) == "AWAY"
    stored = db.collection("whatsappManualAvailability").document(target_phone_id).get().to_dict()
    assert stored["updatedByUid"] == "owner-uid"

    away_event = _whatsapp_text_event(
        target_phone_id, "wamid.runtime-away", "15554440001", "Reply now"
    )
    assert _post_whatsapp_event(client, away_event).status_code == 200
    assert len(generated) == 1
    assert sent == [target_phone_id]

    available_update = client.post(
        "/api/chief-owner/whatsapp-away-mode",
        json={"mode": "AVAILABLE"},
        headers=headers,
    )
    assert available_update.status_code == 200
    available_event = _whatsapp_text_event(
        target_phone_id, "wamid.runtime-available", "15554440001", "Stop replying"
    )
    assert _post_whatsapp_event(client, available_event).status_code == 200
    assert len(generated) == 1
    assert sent == [target_phone_id]

    readback = client.get(
        "/api/chief-owner/whatsapp-away-mode",
        headers=headers,
    )
    assert readback.status_code == 200
    assert readback.get_json()["mode"] == "AVAILABLE"
    assert readback.get_json()["persistedMode"] == "AVAILABLE"
    assert readback.get_json()["effectiveMode"] == "AVAILABLE"


def test_unauthorized_users_cannot_change_whatsapp_mode(monkeypatch):
    app_module = import_module("backend.app")
    target_phone_id = "15550000141"
    db = _FakeFirestore()
    _configure_manual_away_mode(monkeypatch, app_module, target_phone_id, db)
    _authorize_test_chief_owner(
        monkeypatch,
        app_module,
        email="regular-user@example.com",
    )
    client = app_module.app.test_client()

    missing_auth = client.post(
        "/api/chief-owner/whatsapp-away-mode",
        json={"mode": "AWAY"},
    )
    non_owner = client.post(
        "/api/chief-owner/whatsapp-away-mode",
        json={"mode": "AWAY"},
        headers={"Authorization": "Bearer test-firebase-id-token"},
    )

    assert missing_auth.status_code == 401
    assert non_owner.status_code == 403
    assert db.store == {}


def test_whatsapp_mode_api_requires_configured_sender_and_valid_mode(monkeypatch):
    app_module = import_module("backend.app")
    db = _FakeFirestore()
    _configure_whatsapp(monkeypatch, app_module, {})
    monkeypatch.setitem(app_module.app.config, "WHATSAPP_AWAY_PHONE_NUMBER_ID", "")
    monkeypatch.setattr(app_module, "MI_FIREBASE_DB", db)
    _, headers = _authorize_test_chief_owner(monkeypatch, app_module)
    client = app_module.app.test_client()

    unconfigured = client.get(
        "/api/chief-owner/whatsapp-away-mode",
        headers=headers,
    )
    assert unconfigured.status_code == 200
    assert unconfigured.get_json()["configured"] is False
    assert unconfigured.get_json()["mode"] == "AVAILABLE"

    rejected = client.post(
        "/api/chief-owner/whatsapp-away-mode",
        json={"mode": "SLEEPING"},
        headers=headers,
    )
    assert rejected.status_code == 503
    assert db.store == {}


def test_whatsapp_mode_update_fails_when_firestore_does_not_persist(monkeypatch):
    app_module = import_module("backend.app")
    target_phone_id = "15550000151"
    _configure_whatsapp(
        monkeypatch,
        app_module,
        {target_phone_id: "test-away-token"},
    )
    monkeypatch.setitem(
        app_module.app.config,
        "WHATSAPP_AWAY_PHONE_NUMBER_ID",
        target_phone_id,
    )
    _, headers = _authorize_test_chief_owner(monkeypatch, app_module)

    class NonPersistingDocument:
        def get(self):
            return _FakeFirestoreSnapshot(None)

        def set(self, value, merge=False):
            return None

    class NonPersistingCollection:
        def document(self, document_id):
            return NonPersistingDocument()

    class NonPersistingFirestore:
        def collection(self, collection_name):
            return NonPersistingCollection()

    monkeypatch.setattr(
        app_module,
        "MI_FIREBASE_DB",
        NonPersistingFirestore(),
    )

    response = app_module.app.test_client().post(
        "/api/chief-owner/whatsapp-away-mode",
        json={"mode": "AWAY"},
        headers=headers,
    )

    assert response.status_code == 503
    assert response.get_json()["ok"] is False
    assert "mode" not in response.get_json()


def test_whatsapp_invalid_saved_mode_fails_closed(monkeypatch):
    app_module = import_module("backend.app")
    target_phone_id = "15550000161"
    db = _FakeFirestore()
    db.collection("whatsappManualAvailability").document(target_phone_id).set({
        "phoneNumberId": "different-sender",
        "mode": "AWAY",
    })
    _configure_manual_away_mode(monkeypatch, app_module, target_phone_id, db)
    generated = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: generated.append(payload),
    )
    event = _whatsapp_text_event(
        target_phone_id,
        "wamid.invalid-mode",
        "15556660001",
        "Do not reply",
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 200
    assert generated == []
    assert app_module._whatsapp_manual_mode(target_phone_id) == "AVAILABLE"


def test_whatsapp_status_only_events_never_invoke_ai(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000171"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    ai_requests = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: ai_requests.append(payload),
    )
    event = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": phone_id},
                    "statuses": [{"id": "wamid.sent", "status": "delivered"}],
                },
            }],
        }],
    }

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 200
    assert ai_requests == []


def test_whatsapp_available_switch_during_generation_suppresses_send(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000181"
    db = _FakeFirestore()
    db.collection("whatsappManualAvailability").document(phone_id).set({
        "phoneNumberId": phone_id,
        "mode": "AWAY",
    })
    _configure_manual_away_mode(monkeypatch, app_module, phone_id, db)
    sent = []

    def switch_to_available(payload):
        db.collection("whatsappManualAvailability").document(phone_id).set({
            "phoneNumberId": phone_id,
            "mode": "AVAILABLE",
        })
        return app_module.jsonify({"reply": "Generated but no longer allowed"})

    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        switch_to_available,
    )
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda *args, **kwargs: sent.append(args),
    )
    event = _whatsapp_text_event(
        phone_id, "wamid.mode-changed-during-ai", "15558880001", "Question"
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 200
    assert sent == []


def _configure_coexistence(monkeypatch, app_module, phone_id, waba_id, db):
    _configure_manual_away_mode(monkeypatch, app_module, phone_id, db)
    monkeypatch.setenv("WHATSAPP_WABA_ID", waba_id)


def _coexistence_event(field, value, waba_id="15559999001", event_time=1763000000):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": waba_id,
            "time": event_time,
            "changes": [{"field": field, "value": value}],
        }],
    }


def test_whatsapp_account_update_is_recorded_without_claiming_connection(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000201"
    waba_id = "15559999001"
    db = _FakeFirestore()
    db.collection("whatsappManualAvailability").document(phone_id).set({
        "phoneNumberId": phone_id,
        "mode": "AWAY",
    })
    _configure_coexistence(monkeypatch, app_module, phone_id, waba_id, db)
    ai_requests = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: ai_requests.append(payload),
    )
    event = _coexistence_event(
        "account_update",
        {
            "event": "PARTNER_ADDED",
            "waba_info": {
                "waba_id": waba_id,
                "owner_business_id": "15559999002",
            },
        },
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)
    stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()

    assert response.status_code == 200
    assert stored["mode"] == "AVAILABLE"
    assert stored["manualReviewRequired"] is True
    assert stored["coexistenceEventVersion"] == 1
    assert stored["coexistence_accountUpdate"]["event"] == "PARTNER_ADDED"
    assert stored["coexistence_accountUpdate"]["status"] == "partner_added_unverified"
    assert "connected" not in stored["coexistence_accountUpdate"]["status"]
    assert ai_requests == []

    _, owner_headers = _authorize_test_chief_owner(monkeypatch, app_module)
    owner_status = app_module.app.test_client().get(
        "/api/chief-owner/whatsapp-away-mode",
        headers=owner_headers,
    )
    owner_status_payload = owner_status.get_json()
    assert owner_status.status_code == 200
    assert owner_status_payload["coexistenceStatus"] == "partner_added_unverified"
    assert "wabaId" not in owner_status_payload
    assert "owner_business_id" not in owner_status_payload


def test_whatsapp_coexistence_revision_increments_and_preserves_other_fields(
    monkeypatch,
):
    app_module = import_module("backend.app")
    phone_id = "15550000218"
    waba_id = "15559999018"
    db = _FakeFirestore()
    db.collection("whatsappManualAvailability").document(phone_id).set({
        "phoneNumberId": phone_id,
        "mode": "AWAY",
        "unrelatedAvailabilityField": "preserve-me",
    })
    _configure_coexistence(monkeypatch, app_module, phone_id, waba_id, db)
    client = app_module.app.test_client()

    revisions = []
    for event_time, event_name in enumerate(
        ("PARTNER_ADDED", "PARTNER_REMOVED", "ACCOUNT_RECONNECTED"),
        start=1763000010,
    ):
        event = _coexistence_event(
            "account_update",
            {
                "event": event_name,
                "waba_info": {"waba_id": waba_id},
            },
            waba_id=waba_id,
            event_time=event_time,
        )
        response = _post_whatsapp_event(client, event)
        stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()
        assert response.status_code == 200
        revisions.append(stored["coexistenceEventVersion"])

    assert revisions == [1, 2, 3]
    assert stored["unrelatedAvailabilityField"] == "preserve-me"
    assert stored["mode"] == "AVAILABLE"
    assert stored["manualReviewRequired"] is True


def test_whatsapp_account_removed_and_reconnected_never_restore_away(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000211"
    waba_id = "15559999011"
    db = _FakeFirestore()
    db.collection("whatsappManualAvailability").document(phone_id).set({
        "phoneNumberId": phone_id,
        "mode": "AWAY",
    })
    _configure_coexistence(monkeypatch, app_module, phone_id, waba_id, db)
    client = app_module.app.test_client()
    revisions = []

    for event_name in ("PARTNER_REMOVED", "ACCOUNT_RECONNECTED"):
        event = _coexistence_event(
            "account_update",
            {
                "event": event_name,
                "waba_info": {"waba_id": waba_id},
            },
        )
        response = _post_whatsapp_event(client, event)
        stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()
        assert response.status_code == 200
        assert stored["mode"] == "AVAILABLE"
        revisions.append(stored["coexistenceEventVersion"])

    stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()
    assert revisions == [1, 2]
    assert stored["coexistence_accountUpdate"]["event"] == "ACCOUNT_RECONNECTED"
    assert stored["coexistence_accountUpdate"]["status"] == "reconnected_needs_review"
    assert stored["manualReviewRequired"] is True
    db.collection("whatsappManualAvailability").document(phone_id).set({
        "mode": "AWAY",
        "manualReviewRequired": False,
        "manualReviewConfirmedAt": None,
    }, merge=True)
    assert app_module._whatsapp_manual_mode(phone_id) == "AVAILABLE"

    _, owner_headers = _authorize_test_chief_owner(monkeypatch, app_module)
    client = app_module.app.test_client()
    status = client.get(
        "/api/chief-owner/whatsapp-away-mode",
        headers=owner_headers,
    )
    assert status.status_code == 200
    assert status.get_json()["persistedMode"] == "AWAY"
    assert status.get_json()["effectiveMode"] == "AVAILABLE"
    assert status.get_json()["manualReviewRequired"] is True
    review_version = status.get_json()["reviewVersion"]
    assert type(review_version) is int

    blocked = client.post(
        "/api/chief-owner/whatsapp-away-mode",
        json={"mode": "AWAY"},
        headers=owner_headers,
    )
    assert blocked.status_code == 409
    assert blocked.get_json()["code"] == "MANUAL_REVIEW_REQUIRED"
    assert app_module._whatsapp_manual_mode(phone_id) == "AVAILABLE"

    reviewed = client.post(
        "/api/chief-owner/whatsapp-away-mode",
        json={
            "mode": "AWAY",
            "reviewConfirmed": True,
            "reviewVersion": review_version,
        },
        headers=owner_headers,
    )
    assert reviewed.status_code == 200
    assert reviewed.get_json()["manualReviewRequired"] is False
    stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()
    assert stored["mode"] == "AWAY"
    assert stored["manualReviewRequired"] is False
    assert stored["manualReviewConfirmedByUid"] == "owner-uid"
    assert type(stored["coexistenceEventVersion"]) is int
    assert stored["coexistenceEventVersion"] == review_version
    assert stored["coexistence_accountUpdate"]["status"] == "reconnected_needs_review"
    status = client.get(
        "/api/chief-owner/whatsapp-away-mode",
        headers=owner_headers,
    )
    assert status.get_json()["coexistenceStatus"] == "manual_review_completed_unverified"


def test_whatsapp_owner_confirmation_rejects_event_received_before_confirmation(
    monkeypatch,
):
    app_module = import_module("backend.app")
    phone_id = "15550000212"
    waba_id = "15559999012"
    db = _FakeFirestore()
    _configure_coexistence(monkeypatch, app_module, phone_id, waba_id, db)
    _, owner_headers = _authorize_test_chief_owner(monkeypatch, app_module)
    client = app_module.app.test_client()

    first_event = _coexistence_event(
        "account_update",
        {
            "event": "PARTNER_ADDED",
            "waba_info": {"waba_id": waba_id},
        },
        waba_id=waba_id,
    )
    assert _post_whatsapp_event(client, first_event).status_code == 200
    status = client.get(
        "/api/chief-owner/whatsapp-away-mode",
        headers=owner_headers,
    )
    stale_version = status.get_json()["reviewVersion"]

    newer_event = _coexistence_event(
        "account_update",
        {
            "event": "PARTNER_REMOVED",
            "waba_info": {"waba_id": waba_id},
        },
        waba_id=waba_id,
        event_time=1763000001,
    )
    assert _post_whatsapp_event(client, newer_event).status_code == 200

    response = client.post(
        "/api/chief-owner/whatsapp-away-mode",
        json={
            "mode": "AWAY",
            "reviewConfirmed": True,
            "reviewVersion": stale_version,
        },
        headers=owner_headers,
    )
    stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()

    assert response.status_code == 409
    assert response.get_json()["code"] == "STALE_REVIEW_CONFIRMATION"
    assert stored["coexistence_accountUpdate"]["event"] == "PARTNER_REMOVED"
    assert stored["coexistenceEventVersion"] == stale_version + 1
    assert stored["manualReviewRequired"] is True
    assert stored["manualReviewConfirmedAt"] is None


def test_whatsapp_owner_confirmation_retries_conflict_with_new_account_event(
    monkeypatch,
):
    app_module = import_module("backend.app")
    phone_id = "15550000213"
    waba_id = "15559999013"
    db = _FakeFirestore()
    _configure_coexistence(monkeypatch, app_module, phone_id, waba_id, db)
    _, owner_headers = _authorize_test_chief_owner(monkeypatch, app_module)
    client = app_module.app.test_client()

    first_event = _coexistence_event(
        "account_update",
        {
            "event": "PARTNER_ADDED",
            "waba_info": {"waba_id": waba_id},
        },
        waba_id=waba_id,
    )
    assert _post_whatsapp_event(client, first_event).status_code == 200
    status = client.get(
        "/api/chief-owner/whatsapp-away-mode",
        headers=owner_headers,
    )
    stale_version = status.get_json()["reviewVersion"]
    injected = False

    def receive_new_event_before_commit():
        nonlocal injected
        if injected:
            return
        injected = True
        newer_event = _coexistence_event(
            "account_update",
            {
                "event": "ACCOUNT_RECONNECTED",
                "waba_info": {"waba_id": waba_id},
            },
            waba_id=waba_id,
            event_time=1763000002,
        )
        response = _post_whatsapp_event(client, newer_event)
        assert response.status_code == 200

    db.transaction_attempt_hook = receive_new_event_before_commit
    response = client.post(
        "/api/chief-owner/whatsapp-away-mode",
        json={
            "mode": "AWAY",
            "reviewConfirmed": True,
            "reviewVersion": stale_version,
        },
        headers=owner_headers,
    )
    stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()

    assert response.status_code == 409
    assert response.get_json()["code"] == "STALE_REVIEW_CONFIRMATION"
    assert injected is True
    assert db.transaction_attempts >= 4
    assert stored["coexistence_accountUpdate"]["event"] == "ACCOUNT_RECONNECTED"
    assert stored["coexistenceEventVersion"] == stale_version + 1
    assert stored["manualReviewRequired"] is True
    assert stored["manualReviewConfirmedAt"] is None


def test_whatsapp_concurrent_account_updates_retry_and_preserve_review_requirement(
    monkeypatch,
):
    app_module = import_module("backend.app")
    phone_id = "15550000214"
    waba_id = "15559999014"
    db = _FakeFirestore()
    _configure_coexistence(monkeypatch, app_module, phone_id, waba_id, db)
    barrier = Barrier(2)
    thread_state = local()

    def synchronize_first_attempt():
        if getattr(thread_state, "synchronized", False):
            return
        thread_state.synchronized = True
        barrier.wait(timeout=5)

    db.transaction_attempt_hook = synchronize_first_attempt
    summaries = (
        {"event": "PARTNER_ADDED"},
        {"event": "PARTNER_REMOVED"},
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                app_module._save_whatsapp_coexistence_summary,
                phone_id,
                "accountUpdate",
                summary,
                "AVAILABLE",
                True,
            )
            for summary in summaries
        ]
        for future in futures:
            future.result(timeout=10)

    stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()
    assert db.transaction_attempts == 3
    assert db.committed_revisions == [1, 2]
    assert stored["manualReviewRequired"] is True
    assert stored["mode"] == "AVAILABLE"
    assert stored["coexistence_accountUpdate"]["event"] in {
        "PARTNER_ADDED",
        "PARTNER_REMOVED",
    }
    assert stored["coexistenceEventVersion"] == 2


def test_whatsapp_firestore_failure_does_not_confirm_manual_review(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000215"
    db = _FailOnTransactionNumber(fail_on=1)
    db.collection("whatsappManualAvailability").document(phone_id).set({
        "phoneNumberId": phone_id,
        "mode": "AVAILABLE",
        "coexistence_accountUpdate": {
            "event": "PARTNER_ADDED",
            "status": "partner_added_unverified",
        },
        "coexistenceEventVersion": 1,
        "manualReviewRequired": True,
        "manualReviewConfirmedAt": None,
    })
    _configure_manual_away_mode(monkeypatch, app_module, phone_id, db)
    _, owner_headers = _authorize_test_chief_owner(monkeypatch, app_module)

    response = app_module.app.test_client().post(
        "/api/chief-owner/whatsapp-away-mode",
        json={
            "mode": "AWAY",
            "reviewConfirmed": True,
            "reviewVersion": 1,
        },
        headers=owner_headers,
    )
    stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()

    assert response.status_code == 503
    assert stored["mode"] == "AVAILABLE"
    assert stored["manualReviewRequired"] is True
    assert stored["manualReviewConfirmedAt"] is None


def test_unauthorized_user_cannot_confirm_whatsapp_manual_review(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000217"
    db = _FakeFirestore()
    db.collection("whatsappManualAvailability").document(phone_id).set({
        "phoneNumberId": phone_id,
        "mode": "AVAILABLE",
        "coexistenceEventVersion": 1,
        "manualReviewRequired": True,
        "manualReviewConfirmedAt": None,
    })
    _configure_manual_away_mode(monkeypatch, app_module, phone_id, db)
    _, unauthorized_headers = _authorize_test_chief_owner(
        monkeypatch,
        app_module,
        email="unauthorized@example.com",
    )

    response = app_module.app.test_client().post(
        "/api/chief-owner/whatsapp-away-mode",
        json={
            "mode": "AWAY",
            "reviewConfirmed": True,
            "reviewVersion": 1,
        },
        headers=unauthorized_headers,
    )
    stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()

    assert response.status_code == 403
    assert stored["mode"] == "AVAILABLE"
    assert stored["manualReviewRequired"] is True
    assert stored["manualReviewConfirmedAt"] is None


_FIRESTORE_INT64_MAX = (1 << 63) - 1


@pytest.mark.parametrize(
    "submitted_revision",
    [
        pytest.param("missing", id="missing"),
        pytest.param(None, id="null"),
        pytest.param(-1, id="negative"),
        pytest.param(True, id="boolean"),
        pytest.param("1", id="malformed-string"),
        pytest.param(1.5, id="non-integer"),
        pytest.param(_FIRESTORE_INT64_MAX + 1, id="out-of-range"),
    ],
)
def test_invalid_whatsapp_confirmation_revision_is_rejected(
    monkeypatch,
    submitted_revision,
):
    app_module = import_module("backend.app")
    phone_id = "15550000219"
    db = _FakeFirestore()
    document = db.collection("whatsappManualAvailability").document(phone_id)
    document.set({
        "phoneNumberId": phone_id,
        "mode": "AVAILABLE",
        "coexistence_accountUpdate": {
            "event": "PARTNER_ADDED",
            "status": "partner_added_unverified",
        },
        "coexistenceEventVersion": 1,
        "manualReviewRequired": True,
        "manualReviewConfirmedAt": None,
    })
    original = document.get().to_dict()
    _configure_manual_away_mode(monkeypatch, app_module, phone_id, db)
    _, owner_headers = _authorize_test_chief_owner(monkeypatch, app_module)
    payload = {"mode": "AWAY", "reviewConfirmed": True}
    if submitted_revision != "missing":
        payload["reviewVersion"] = submitted_revision

    response = app_module.app.test_client().post(
        "/api/chief-owner/whatsapp-away-mode",
        json=payload,
        headers=owner_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_REVIEW_VERSION"
    assert document.get().to_dict() == original


@pytest.mark.parametrize(
    "stored_revision",
    [
        pytest.param(None, id="null"),
        pytest.param(True, id="boolean"),
        pytest.param(-1, id="negative"),
        pytest.param(1.0, id="float"),
        pytest.param("legacy-uuid-version", id="legacy-uuid"),
        pytest.param(_FIRESTORE_INT64_MAX + 1, id="out-of-range"),
    ],
)
def test_invalid_stored_whatsapp_revision_fails_closed(
    monkeypatch,
    stored_revision,
):
    app_module = import_module("backend.app")
    phone_id = "15550000220"
    db = _FakeFirestore()
    document = db.collection("whatsappManualAvailability").document(phone_id)
    document.set({
        "phoneNumberId": phone_id,
        "mode": "AWAY",
        "coexistence_accountUpdate": {
            "event": "PARTNER_ADDED",
            "status": "partner_added_unverified",
        },
        "coexistenceEventVersion": stored_revision,
        "manualReviewRequired": True,
        "manualReviewConfirmedAt": None,
        "unrelatedAvailabilityField": "preserve-me",
    })
    original = document.get().to_dict()
    _configure_manual_away_mode(monkeypatch, app_module, phone_id, db)
    _, owner_headers = _authorize_test_chief_owner(monkeypatch, app_module)
    client = app_module.app.test_client()

    status = client.get(
        "/api/chief-owner/whatsapp-away-mode",
        headers=owner_headers,
    )
    response = client.post(
        "/api/chief-owner/whatsapp-away-mode",
        json={
            "mode": "AWAY",
            "reviewConfirmed": True,
            "reviewVersion": 1,
        },
        headers=owner_headers,
    )

    assert status.status_code == 200
    assert status.get_json()["stateSource"] == "invalid"
    assert status.get_json()["effectiveMode"] == "AVAILABLE"
    assert status.get_json()["manualReviewRequired"] is True
    assert status.get_json()["reviewVersion"] is None
    assert response.status_code == 503
    assert document.get().to_dict() == original
    with pytest.raises(RuntimeError, match="revision is invalid"):
        app_module._save_whatsapp_coexistence_summary(
            phone_id,
            "accountUpdate",
            {"event": "PARTNER_REMOVED"},
            mode="AVAILABLE",
            manual_review_required=True,
        )
    assert document.get().to_dict() == original


def test_maximum_whatsapp_revision_can_be_confirmed(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000221"
    db = _FakeFirestore()
    db.collection("whatsappManualAvailability").document(phone_id).set({
        "phoneNumberId": phone_id,
        "mode": "AVAILABLE",
        "coexistence_accountUpdate": {
            "event": "PARTNER_ADDED",
            "status": "partner_added_unverified",
        },
        "coexistenceEventVersion": _FIRESTORE_INT64_MAX,
        "manualReviewRequired": True,
        "manualReviewConfirmedAt": None,
    })
    _configure_manual_away_mode(monkeypatch, app_module, phone_id, db)
    _, owner_headers = _authorize_test_chief_owner(monkeypatch, app_module)
    client = app_module.app.test_client()

    status = client.get(
        "/api/chief-owner/whatsapp-away-mode",
        headers=owner_headers,
    )
    response = client.post(
        "/api/chief-owner/whatsapp-away-mode",
        json={
            "mode": "AWAY",
            "reviewConfirmed": True,
            "reviewVersion": _FIRESTORE_INT64_MAX,
        },
        headers=owner_headers,
    )
    stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()

    assert status.get_json()["reviewVersion"] == _FIRESTORE_INT64_MAX
    assert type(status.get_json()["reviewVersion"]) is int
    assert response.status_code == 200
    assert stored["coexistenceEventVersion"] == _FIRESTORE_INT64_MAX
    assert stored["manualReviewRequired"] is False


def test_whatsapp_revision_overflow_does_not_write_event(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000222"
    db = _FakeFirestore()
    document = db.collection("whatsappManualAvailability").document(phone_id)
    document.set({
        "phoneNumberId": phone_id,
        "mode": "AVAILABLE",
        "coexistenceEventVersion": _FIRESTORE_INT64_MAX - 1,
        "unrelatedAvailabilityField": "preserve-me",
    })
    _configure_manual_away_mode(monkeypatch, app_module, phone_id, db)

    app_module._save_whatsapp_coexistence_summary(
        phone_id,
        "accountUpdate",
        {"event": "PARTNER_ADDED"},
        mode="AVAILABLE",
        manual_review_required=True,
    )
    at_maximum = document.get().to_dict()
    assert at_maximum["coexistenceEventVersion"] == _FIRESTORE_INT64_MAX
    assert at_maximum["unrelatedAvailabilityField"] == "preserve-me"

    with pytest.raises(RuntimeError, match="revision is exhausted"):
        app_module._save_whatsapp_coexistence_summary(
            phone_id,
            "accountUpdate",
            {"event": "PARTNER_REMOVED"},
            mode="AVAILABLE",
            manual_review_required=True,
        )

    assert document.get().to_dict() == at_maximum


def test_unknown_coexistence_account_update_fails_closed(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000216"
    waba_id = "15559999016"
    db = _FakeFirestore()
    db.collection("whatsappManualAvailability").document(phone_id).set({
        "phoneNumberId": phone_id,
        "mode": "AWAY",
    })
    _configure_coexistence(monkeypatch, app_module, phone_id, waba_id, db)
    event_name = "EXPERIMENTAL_DISCOVERY_EVENT"
    event = _coexistence_event(
        "account_update",
        {
            "event": event_name,
            "waba_info": {"waba_id": waba_id},
        },
        waba_id=waba_id,
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)
    stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()

    assert response.status_code == 200
    assert stored["mode"] == "AVAILABLE"
    assert stored["manualReviewRequired"] is True
    assert stored["coexistence_accountUpdate"]["event"] == "UNRECOGNIZED"
    assert stored["coexistence_accountUpdate"]["status"] == "manual_review_required"
    assert event_name not in json.dumps(stored)
    assert app_module._whatsapp_manual_mode(phone_id) == "AVAILABLE"


def test_whatsapp_history_sync_is_summary_only_and_never_invokes_ai(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000221"
    waba_id = "15559999021"
    db = _FakeFirestore()
    _configure_coexistence(monkeypatch, app_module, phone_id, waba_id, db)
    ai_requests = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: ai_requests.append(payload),
    )
    history_text = "historical private customer text"
    event = _coexistence_event(
        "history",
        {
            "messaging_product": "whatsapp",
            "metadata": {
                "display_phone_number": "15550000221",
                "phone_number_id": phone_id,
            },
            "history": [{
                "metadata": {"phase": 0, "chunk_order": 2, "progress": 55},
                "threads": [{
                    "id": "15558880001",
                    "context": {"wa_id": "15558880001"},
                    "messages": [{
                        "from": "15558880001",
                        "id": "wamid.history-customer-message",
                        "timestamp": "1762999000",
                        "type": "text",
                        "text": {"body": history_text},
                        "history_context": {"status": "read"},
                    }],
                }],
            }],
        },
        waba_id=waba_id,
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)
    stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()
    summary = stored["coexistence_history"]

    assert response.status_code == 200
    assert summary["batchesObserved"] == 1
    assert summary["threadsObserved"] == 1
    assert summary["messagesObserved"] == 1
    assert summary["phasesObserved"] == [0]
    assert summary["chunkOrdersObserved"] == [2]
    assert summary["maxProgressObserved"] == 55
    assert ai_requests == []
    assert history_text not in json.dumps(stored)
    assert "wamid.history-customer-message" not in json.dumps(stored)
    assert "15558880001" not in json.dumps(stored)


def test_whatsapp_history_sync_failure_is_recorded_without_guessing_completion(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000231"
    waba_id = "15559999031"
    db = _FakeFirestore()
    _configure_coexistence(monkeypatch, app_module, phone_id, waba_id, db)
    event = _coexistence_event(
        "history",
        {
            "messaging_product": "whatsapp",
            "metadata": {"phone_number_id": phone_id},
            "history": [{
                "errors": [{
                    "code": 2593109,
                    "title": "History sync declined",
                    "message": "History sharing is turned off",
                }],
            }],
        },
        waba_id=waba_id,
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)
    stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()

    assert response.status_code == 200
    assert stored["coexistence_history"]["errorCodes"] == [2593109]
    assert stored["coexistence_history"]["maxProgressObserved"] is None
    assert "History sharing is turned off" not in json.dumps(stored)


def test_whatsapp_app_state_sync_stores_counts_not_contact_data(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000241"
    waba_id = "15559999041"
    db = _FakeFirestore()
    _configure_coexistence(monkeypatch, app_module, phone_id, waba_id, db)
    private_contact_name = "Private Test Contact"
    private_contact_number = "15558880041"
    event = _coexistence_event(
        "smb_app_state_sync",
        {
            "messaging_product": "whatsapp",
            "metadata": {"phone_number_id": phone_id},
            "state_sync": [
                {
                    "type": "contact",
                    "contact": {
                        "full_name": private_contact_name,
                        "phone_number": private_contact_number,
                        "user_id": "BSUID-private",
                    },
                    "action": "add",
                    "metadata": {"timestamp": "1762999000"},
                },
                {
                    "type": "contact",
                    "contact": {"full_name": private_contact_name},
                    "action": "remove",
                    "metadata": {"timestamp": "1762999001"},
                },
            ],
        },
        waba_id=waba_id,
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)
    stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()
    summary = stored["coexistence_smb_app_state_sync"]

    assert response.status_code == 200
    assert summary["contactEventsObserved"] == 2
    assert summary["addEventsObserved"] == 1
    assert summary["removeEventsObserved"] == 1
    assert summary["lastItemTimestamp"] == 1762999001
    assert private_contact_name not in json.dumps(stored)
    assert private_contact_number not in json.dumps(stored)
    assert "BSUID-private" not in json.dumps(stored)


def test_whatsapp_business_app_echoes_never_invoke_ai_or_send_replies(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000251"
    waba_id = "15559999051"
    db = _FakeFirestore()
    db.collection("whatsappManualAvailability").document(phone_id).set({
        "phoneNumberId": phone_id,
        "mode": "AWAY",
    })
    _configure_coexistence(monkeypatch, app_module, phone_id, waba_id, db)
    ai_requests = []
    sent = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: ai_requests.append(payload),
    )
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda *args, **kwargs: sent.append(args),
    )
    private_echo_text = "Business App message that must not loop"
    event = _coexistence_event(
        "smb_message_echoes",
        {
            "messaging_product": "whatsapp",
            "metadata": {"phone_number_id": phone_id},
            "contacts": [{"wa_id": "15558880051"}],
            "message_echoes": [{
                "from": "15550000251",
                "to": "15558880051",
                "id": "wamid.business-app-echo",
                "timestamp": "1762999000",
                "type": "text",
                "text": {"body": private_echo_text},
            }],
        },
        waba_id=waba_id,
    )
    client = app_module.app.test_client()

    first = _post_whatsapp_event(client, event)
    duplicate = _post_whatsapp_event(client, event)
    stored = db.collection("whatsappManualAvailability").document(phone_id).get().to_dict()

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert stored["mode"] == "AWAY"
    assert stored["coexistence_smb_message_echoes"]["echoesObserved"] == 1
    assert ai_requests == []
    assert sent == []
    assert private_echo_text not in json.dumps(stored)
    assert "15558880051" not in json.dumps(stored)
    assert "wamid.business-app-echo" not in json.dumps(stored)


def test_whatsapp_coexistence_events_ignore_unknown_sender_or_waba(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000261"
    waba_id = "15559999061"
    db = _FakeFirestore()
    _configure_coexistence(monkeypatch, app_module, phone_id, waba_id, db)
    event = _coexistence_event(
        "smb_message_echoes",
        {
            "metadata": {"phone_number_id": "15550000999"},
            "message_echoes": [],
        },
        waba_id="15559999999",
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 200
    assert db.store == {}


def test_whatsapp_coexistence_firestore_failure_is_retryable_and_safe(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000271"
    waba_id = "15559999071"
    _configure_coexistence(monkeypatch, app_module, phone_id, waba_id, None)
    monkeypatch.setattr(app_module, "MI_FIREBASE_DB", None)
    ai_requests = []
    sent = []
    monkeypatch.setattr(
        app_module,
        "_handle_chat_request",
        lambda payload: ai_requests.append(payload),
    )
    monkeypatch.setattr(
        app_module,
        "_send_whatsapp_text",
        lambda *args, **kwargs: sent.append(args),
    )
    event = _coexistence_event(
        "account_update",
        {
            "event": "ACCOUNT_RECONNECTED",
            "waba_info": {"waba_id": waba_id},
        },
        waba_id=waba_id,
    )

    response = _post_whatsapp_event(app_module.app.test_client(), event)

    assert response.status_code == 502
    assert ai_requests == []
    assert sent == []
    assert app_module._whatsapp_manual_mode(phone_id) == "AVAILABLE"


def test_embedded_signup_readiness_requires_chief_owner(monkeypatch):
    app_module = import_module("backend.app")
    _authorize_test_chief_owner(
        monkeypatch,
        app_module,
        email="regular-user@example.com",
    )
    client = app_module.app.test_client()

    unauthenticated = client.get(
        "/api/chief-owner/whatsapp-embedded-signup/readiness"
    )
    unauthorized = client.get(
        "/api/chief-owner/whatsapp-embedded-signup/readiness",
        headers={"Authorization": "Bearer test-firebase-id-token"},
    )

    assert unauthenticated.status_code == 401
    assert unauthorized.status_code == 403


def test_embedded_signup_readiness_reports_missing_names_only(monkeypatch):
    app_module = import_module("backend.app")
    required = [
        "META_APP_ID",
        "META_EMBEDDED_SIGNUP_CONFIG_ID",
        "META_EMBEDDED_SIGNUP_VERSION",
        "META_EMBEDDED_SIGNUP_ENABLED",
        "WHATSAPP_APP_SECRET",
        "WHATSAPP_ID_HMAC_KEY",
        "WHATSAPP_VERIFY_TOKEN",
        "WHATSAPP_GRAPH_API_VERSION",
        "WHATSAPP_WABA_ID",
        "GROQ_API_KEY",
        "WHATSAPP_SENDERS_JSON",
        "WHATSAPP_AWAY_PHONE_NUMBER_ID",
    ]
    for setting in required:
        monkeypatch.delenv(setting, raising=False)
    monkeypatch.setitem(app_module.app.config, "WHATSAPP_AWAY_PHONE_NUMBER_ID", "")
    monkeypatch.setitem(
        app_module.app.config,
        "WHATSAPP_SENDER_IDS_PROVIDER",
        lambda: {},
    )
    _, headers = _authorize_test_chief_owner(monkeypatch, app_module)

    response = app_module.app.test_client().get(
        "/api/chief-owner/whatsapp-embedded-signup/readiness",
        headers=headers,
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "configuration_incomplete"
    assert payload["configurationReady"] is False
    assert payload["launchEnabled"] is False
    assert payload["metaApproval"] == "not_verified"
    assert payload["connectionStatus"] == "not_verified"
    assert payload["secureTokenStorageReady"] is False
    assert payload["secureTokenStorageStatus"] == "unavailable"
    assert payload["webhookSubscriptionStatus"] == "unknown"
    assert payload["eligibilityStatus"] == "unknown"
    assert payload["signupStatus"] == "not_started"
    assert payload["localWebhookStatus"] == "configuration_incomplete"
    assert payload["missingSettings"] == required
    assert "META_APP_ID_VALUE" not in json.dumps(payload)


def test_embedded_signup_never_launches_without_exchange_storage(monkeypatch):
    app_module = import_module("backend.app")
    values = {
        "META_APP_ID": "test-public-app-id",
        "META_EMBEDDED_SIGNUP_CONFIG_ID": "test-config-id",
        "META_EMBEDDED_SIGNUP_VERSION": "v5",
        "META_EMBEDDED_SIGNUP_ENABLED": "true",
        "WHATSAPP_APP_SECRET": "test-app-secret",
        "WHATSAPP_ID_HMAC_KEY": "test-stable-id-hmac-key-0123456789",
        "WHATSAPP_VERIFY_TOKEN": "test-verify-token",
        "WHATSAPP_GRAPH_API_VERSION": "v27.0",
        "WHATSAPP_WABA_ID": "15559999001",
        "WHATSAPP_SENDERS_JSON": '{"15550000299":"test-sender-token"}',
        "GROQ_API_KEY": "test-ai-key",
    }
    for setting, value in values.items():
        monkeypatch.setenv(setting, value)
    monkeypatch.setitem(
        app_module.app.config,
        "WHATSAPP_AWAY_PHONE_NUMBER_ID",
        "15550000299",
    )
    monkeypatch.setitem(
        app_module.app.config,
        "WHATSAPP_SENDER_IDS_PROVIDER",
        app_module._load_whatsapp_senders,
    )
    _, headers = _authorize_test_chief_owner(monkeypatch, app_module)

    response = app_module.app.test_client().get(
        "/api/chief-owner/whatsapp-embedded-signup/readiness",
        headers=headers,
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "configuration_present_approval_unverified"
    assert payload["configurationReady"] is True
    assert payload["enabledByConfiguration"] is True
    assert payload["launchEnabled"] is False
    assert payload["secureTokenStorageReady"] is False
    assert payload["secureTokenStorageStatus"] == "unavailable"
    assert payload["senderConfigurationStatus"] == "configured"
    assert payload["designatedSenderConfigured"] is True
    assert payload["localWebhookStatus"] == "configured"
    assert payload["webhookSubscriptionStatus"] == "unknown"
    assert payload["metaApproval"] == "not_verified"
    assert payload["connectionStatus"] == "not_verified"
    assert "test-app-secret" not in json.dumps(payload)
    assert "test-config-id" not in json.dumps(payload)


def test_embedded_signup_rejects_unsupported_version_for_readiness(monkeypatch):
    app_module = import_module("backend.app")
    monkeypatch.setenv("META_APP_ID", "test-public-app-id")
    monkeypatch.setenv("META_EMBEDDED_SIGNUP_CONFIG_ID", "test-config-id")
    monkeypatch.setenv("META_EMBEDDED_SIGNUP_VERSION", "v3")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test-app-secret")
    _, headers = _authorize_test_chief_owner(monkeypatch, app_module)

    response = app_module.app.test_client().get(
        "/api/chief-owner/whatsapp-embedded-signup/readiness",
        headers=headers,
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "configuration_error"
    assert payload["configurationReady"] is False
    assert payload["unsupportedSettings"] == ["META_EMBEDDED_SIGNUP_VERSION"]
    assert payload["launchEnabled"] is False


def test_embedded_signup_rejects_malformed_graph_version(monkeypatch):
    app_module = import_module("backend.app")
    monkeypatch.setenv("META_EMBEDDED_SIGNUP_VERSION", "v5")
    monkeypatch.setenv("WHATSAPP_GRAPH_API_VERSION", "v27")
    monkeypatch.setitem(
        app_module.app.config,
        "WHATSAPP_SENDER_IDS_PROVIDER",
        lambda: {},
    )
    _, headers = _authorize_test_chief_owner(monkeypatch, app_module)

    response = app_module.app.test_client().get(
        "/api/chief-owner/whatsapp-embedded-signup/readiness",
        headers=headers,
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "configuration_error"
    assert payload["invalidSettings"] == ["WHATSAPP_GRAPH_API_VERSION"]
    assert payload["launchEnabled"] is False


def test_whatsapp_identifier_key_is_stable_when_app_secret_rotates(monkeypatch):
    app_module = import_module("backend.app")
    monkeypatch.setenv("WHATSAPP_ID_HMAC_KEY", "stable-test-key-material-at-least-32-bytes")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "old-app-secret")
    original = app_module._whatsapp_hmac_identifier("receipt", ["phone", "customer", "message"])
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "rotated-app-secret")
    rotated = app_module._whatsapp_hmac_identifier("receipt", ["phone", "customer", "message"])
    assert rotated == original


def test_whatsapp_identifier_key_is_required_and_does_not_fall_back(monkeypatch):
    app_module = import_module("backend.app")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "legacy-app-secret")
    monkeypatch.delenv("WHATSAPP_ID_HMAC_KEY", raising=False)
    with pytest.raises(RuntimeError):
        app_module._whatsapp_hmac_identifier("receipt", ["phone", "customer", "message"])


def test_whatsapp_rate_limit_is_rolling_and_caps_ten_messages(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000901"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    database = app_module.MI_FIREBASE_DB
    for index in range(10):
        claim = app_module._whatsapp_claim_message(
            phone_id, "phone", "15551110001", f"wamid.rate-{index}",
            int(datetime.now(timezone.utc).timestamp()), allow_ai=True,
        )
        assert claim["status"] == "claimed"
        assert app_module._whatsapp_release_message(claim, "failed") is True

    limited = app_module._whatsapp_claim_message(
        phone_id, "phone", "15551110001", "wamid.rate-limit",
        int(datetime.now(timezone.utc).timestamp()), allow_ai=True,
    )
    assert limited["status"] == "rate_limited"

    rate_id = app_module._whatsapp_hmac_identifier(
        "rate-limit", [phone_id, "phone", "15551110001"]
    )
    rate_doc = database.store[("whatsappCustomerRateLimits", rate_id)]
    rate_doc["timestamps"] = [datetime.now(timezone.utc).timestamp() - 61]
    database.store[("whatsappCustomerRateLimits", rate_id)] = rate_doc
    accepted = app_module._whatsapp_claim_message(
        phone_id, "phone", "15551110001", "wamid.after-window",
        int(datetime.now(timezone.utc).timestamp()), allow_ai=True,
    )
    assert accepted["status"] == "claimed"


def test_whatsapp_duplicate_redelivery_does_not_consume_rate_quota_twice(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000902"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    args = (
        phone_id, "phone", "15551110002", "wamid.same-message",
        int(datetime.now(timezone.utc).timestamp()),
    )
    first = app_module._whatsapp_claim_message(*args, allow_ai=True)
    assert first["status"] == "claimed"
    assert app_module._whatsapp_release_message(first, "failed") is True
    rate_id = app_module._whatsapp_hmac_identifier(
        "rate-limit", [phone_id, "phone", "15551110002"]
    )
    before = list(
        app_module.MI_FIREBASE_DB.store[
            ("whatsappCustomerRateLimits", rate_id)
        ]["timestamps"]
    )
    second = app_module._whatsapp_claim_message(*args, allow_ai=True)
    assert second["status"] == "claimed"
    after = app_module.MI_FIREBASE_DB.store[
        ("whatsappCustomerRateLimits", rate_id)
    ]["timestamps"]
    assert after == before


def test_whatsapp_ai_concurrency_slots_are_shared_per_sender(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000903"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    claims = []
    for index in range(app_module._WHATSAPP_AI_CONCURRENCY_LIMIT):
        claim = app_module._whatsapp_claim_message(
            phone_id, "phone", f"1555222{index:04d}", f"wamid.slot-{index}",
            int(datetime.now(timezone.utc).timestamp()), allow_ai=True,
        )
        assert claim["status"] == "claimed"
        claims.append(claim)
    blocked = app_module._whatsapp_claim_message(
        phone_id, "phone", "15553330000", "wamid.slot-overflow",
        int(datetime.now(timezone.utc).timestamp()), allow_ai=True,
    )
    assert blocked["status"] == "busy"
    for claim in claims:
        app_module._whatsapp_release_message(claim, "failed")


def test_whatsapp_ambiguous_send_is_never_automatically_retried(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000904"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    monkeypatch.setattr(
        app_module, "_handle_chat_request",
        lambda payload: app_module.jsonify({"reply": "A reply"}),
    )
    send_calls = []

    def ambiguous_send(*args, **kwargs):
        send_calls.append(args)
        raise app_module._WhatsAppSendOutcomeUnknown("ambiguous")

    monkeypatch.setattr(app_module, "_send_whatsapp_text", ambiguous_send)
    event = _whatsapp_text_event(
        phone_id, "wamid.ambiguous-send", "15554440004", "Hello"
    )
    client = app_module.app.test_client()
    first = _post_whatsapp_event(client, event)
    second = _post_whatsapp_event(client, event)
    assert first.status_code == 502
    assert second.status_code == 200
    assert len(send_calls) == 1


def test_whatsapp_stop_command_persists_optout_and_suppresses_ai(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000905"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    ai_calls = []
    monkeypatch.setattr(
        app_module, "_handle_chat_request",
        lambda payload: ai_calls.append(payload),
    )
    client = app_module.app.test_client()
    stop_event = _whatsapp_text_event(
        phone_id, "wamid.stop", "15554440005", "STOP"
    )
    normal_event = _whatsapp_text_event(
        phone_id, "wamid.after-stop", "15554440005", "Hello"
    )
    assert _post_whatsapp_event(client, stop_event).status_code == 200
    assert _post_whatsapp_event(client, normal_event).status_code == 200
    assert ai_calls == []


def test_whatsapp_reconciliation_requires_stale_delivery_unknown(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000906"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    receipt_id = "a" * 64
    database = app_module.MI_FIREBASE_DB
    database.store[("whatsappMessageReceipts", receipt_id)] = {
        "status": "delivery_unknown",
        "sendStartedAt": datetime.now(timezone.utc) - timedelta(minutes=20),
        "lockExpiresAt": datetime.now(timezone.utc) - timedelta(minutes=5),
    }
    result = app_module._whatsapp_reconcile_delivery(
        receipt_id, "not-delivered", "test-operator"
    )
    assert result == "updated"
    assert database.store[("whatsappMessageReceipts", receipt_id)]["status"] == "failed"

    sending_id = "b" * 64
    database.store[("whatsappMessageReceipts", sending_id)] = {
        "status": "sending",
        "sendStartedAt": datetime.now(timezone.utc) - timedelta(minutes=20),
        "lockExpiresAt": datetime.now(timezone.utc) - timedelta(minutes=5),
    }
    assert app_module._whatsapp_reconcile_delivery(
        sending_id, "not-delivered", "test-operator"
    ) == "not-reconcilable"


def test_whatsapp_image_generation_request_never_calls_image_pipeline(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000907"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    ai_calls = []
    sent = []
    monkeypatch.setattr(
        app_module, "_handle_chat_request",
        lambda payload: ai_calls.append(payload),
    )
    monkeypatch.setattr(
        app_module, "_send_whatsapp_text",
        lambda *args, **kwargs: sent.append(args),
    )
    event = _whatsapp_text_event(
        phone_id, "wamid.image-request", "15554440007",
        "Please generate an image of a blue airplane",
    )
    response = _post_whatsapp_event(app_module.app.test_client(), event)
    assert response.status_code == 200
    assert ai_calls == []
    assert len(sent) == 1
    assert "can't generate" in sent[0][2].lower()


def test_whatsapp_stop_during_ai_work_blocks_final_send_authorization(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000908"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    claim = app_module._whatsapp_claim_message(
        phone_id, "phone", "15554440008", "wamid.stop-race",
        int(datetime.now(timezone.utc).timestamp()), allow_ai=True,
    )
    assert claim["status"] == "claimed"
    app_module._whatsapp_set_optout(phone_id, "phone", "15554440008", True)
    assert app_module._whatsapp_authorize_send(claim, phone_id) is False
    assert app_module._whatsapp_release_message(claim, "ignored_available") is True


def test_whatsapp_heartbeat_renews_processing_and_slot_leases(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000909"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    claim = app_module._whatsapp_claim_message(
        phone_id, "phone", "15554440009", "wamid.heartbeat",
        int(datetime.now(timezone.utc).timestamp()), allow_ai=True,
    )
    assert claim["status"] == "claimed"
    assert app_module._whatsapp_renew_message_claim(claim) is True
    receipt = claim["receiptRef"].get().to_dict()
    slot = claim["slotRef"].get().to_dict()
    assert receipt["lockExpiresAt"] > datetime.now(timezone.utc)
    assert slot["lockExpiresAt"] > datetime.now(timezone.utc)


def test_whatsapp_rate_limit_expires_timestamp_at_exact_sixty_second_boundary():
    app_module = import_module("backend.app")
    active = app_module._whatsapp_rate_timestamps(
        {"timestamps": [939.0, 940.0, 941.0, 1000.0]},
        1000.0,
    )
    assert active == [941.0, 1000.0]


def test_whatsapp_identifier_key_rejects_short_values(monkeypatch):
    app_module = import_module("backend.app")
    monkeypatch.setenv("WHATSAPP_ID_HMAC_KEY", "too-short")
    with pytest.raises(RuntimeError):
        app_module._whatsapp_hmac_identifier("receipt", ["customer", "message"])


def test_whatsapp_webhook_rejects_non_ascii_verification_token_without_server_error(monkeypatch):
    app_module = import_module("backend.app")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "valid-token")
    response = app_module.app.test_client().get(
        "/api/whatsapp/webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "tøken",
            "hub.challenge": "challenge",
        },
    )
    assert response.status_code == 403


def test_whatsapp_identifier_key_initialization_preserves_legacy_hmac_ids(monkeypatch):
    app_module = import_module("backend.app")
    legacy_secret = "0123456789abcdef0123456789abcdef"
    values = ["15550000001", "phone", "15551112222", "wamid.legacy"]
    encoded = json.dumps(values, ensure_ascii=True, separators=(",", ":"))
    expected = hmac.new(
        legacy_secret.encode("utf-8"),
        f"mi-cortex-whatsapp:receipt:{encoded}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    monkeypatch.setenv("WHATSAPP_APP_SECRET", legacy_secret)
    monkeypatch.setenv("WHATSAPP_ID_HMAC_KEY", legacy_secret)
    assert app_module._whatsapp_hmac_identifier("receipt", values) == expected


def test_whatsapp_explicit_graph_rejection_is_retryable_without_double_counting(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000910"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    monkeypatch.setattr(
        app_module, "_handle_chat_request",
        lambda payload: app_module.jsonify({"reply": "A reply"}),
    )
    calls = []

    def rejected(*args, **kwargs):
        calls.append(args)
        raise app_module._WhatsAppSendRejected("rejected")

    monkeypatch.setattr(app_module, "_send_whatsapp_text", rejected)
    event = _whatsapp_text_event(
        phone_id, "wamid.definite-rejection", "15554440010", "Hello"
    )
    client = app_module.app.test_client()
    assert _post_whatsapp_event(client, event).status_code == 502
    assert _post_whatsapp_event(client, event).status_code == 502
    assert len(calls) == 2
    rate_id = app_module._whatsapp_hmac_identifier(
        "rate-limit", [phone_id, "phone", "15554440010"]
    )
    timestamps = app_module.MI_FIREBASE_DB.store[
        ("whatsappCustomerRateLimits", rate_id)
    ]["timestamps"]
    assert len(timestamps) == 1


def test_whatsapp_stale_sending_receipt_is_never_reopened(monkeypatch):
    app_module = import_module("backend.app")
    phone_id = "15550000911"
    _configure_whatsapp(monkeypatch, app_module, {phone_id: "test-access-token"})
    message_id = "wamid.stale-sending"
    receipt_id = app_module._whatsapp_hmac_identifier(
        "receipt", [phone_id, "phone", "15554440011", message_id]
    )
    app_module.MI_FIREBASE_DB.store[
        ("whatsappMessageReceipts", receipt_id)
    ] = {
        "status": "sending",
        "lockExpiresAt": datetime.now(timezone.utc) - timedelta(minutes=20),
        "sendStartedAt": datetime.now(timezone.utc) - timedelta(minutes=20),
    }
    ai_calls = []
    sends = []
    monkeypatch.setattr(
        app_module, "_handle_chat_request",
        lambda payload: ai_calls.append(payload),
    )
    monkeypatch.setattr(
        app_module, "_send_whatsapp_text",
        lambda *args, **kwargs: sends.append(args),
    )
    event = _whatsapp_text_event(
        phone_id, message_id, "15554440011", "Hello"
    )
    response = _post_whatsapp_event(app_module.app.test_client(), event)
    assert response.status_code == 200
    assert ai_calls == []
    assert sends == []
