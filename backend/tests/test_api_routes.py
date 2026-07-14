import json
from importlib import import_module


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

    monkeypatch.setattr(app_module, "_get_gemini_client", lambda: FakeClient())

    client = app_module.app.test_client()
    response = client.post("/api/chat", json={"message": "Hello"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["response"] == "Hello from the test client"
    assert payload["reply"] == "Hello from the test client"


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

    monkeypatch.setattr(app_module, "_get_gemini_client", lambda: FakeClient())

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


def test_assistant_info_route_returns_identity_and_contacts():
    app_module = import_module("backend.app")

    client = app_module.app.test_client()
    response = client.get("/api/assistant-info")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["name"] == "MI AI"
    assert payload["creator"] == "M.I. Muhammadh"
    assert payload["owner"] == "M.I. Muhammadh"
    assert payload["developer"] == "M.I. Muhammadh"
    assert payload["creator_age"] == 17
    assert payload["customer_support_email"] == "miai.customerservice@gmail.com"
    assert payload["other_requirements_email"] == "teamofchatbot.miai@gmail.com"
    assert payload["team_whatsapp_number"] == "+94756390621"
