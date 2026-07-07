import html
import json
import os
import re
import shutil
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from groq import Groq

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

try:
    from docx import Document as DocxDocument
except Exception:
    DocxDocument = None

try:
    import pandas as pd
except Exception:
    pd = None

try:
    from pptx import Presentation
except Exception:
    Presentation = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None

app = Flask(__name__)
CORS(app)

client = None


def _get_groq_client():
    global client
    if client is not None:
        return client
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return None
    client = Groq(api_key=api_key)
    return client

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
LOCAL_PERSISTENCE_FILE = Path(__file__).with_name("local_persistence.json")
UPLOAD_DIR = Path(__file__).with_name("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def _load_local_store():
    if LOCAL_PERSISTENCE_FILE.exists():
        try:
            return json.loads(LOCAL_PERSISTENCE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"conversations": [], "messages": []}
    return {"conversations": [], "messages": []}


def _save_local_store(store):
    LOCAL_PERSISTENCE_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")


def _safe_file_name(name):
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', (name or 'upload').strip())
    return safe or 'upload'


def _allowed_file_type(filename, content_type):
    allowed_exts = {'.pdf', '.docx', '.doc', '.txt', '.xlsx', '.xls', '.csv', '.pptx', '.ppt', '.png', '.jpg', '.jpeg', '.webp'}
    allowed_mimes = {
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/msword',
        'text/plain',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
        'text/csv',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'application/vnd.ms-powerpoint',
        'image/png',
        'image/jpeg',
        'image/webp',
    }
    ext = Path(filename or '').suffix.lower()
    return ext in allowed_exts and (not content_type or content_type in allowed_mimes or ext in {'.png', '.jpg', '.jpeg', '.webp'})


def _needs_live_web_search(text):
    if not text:
        return False
    lowered = text.lower()
    patterns = [
        r"\b(latest|current|today|now|live|breaking|recent|this week|this month|upcoming|tonight|weather|news|stock|price|forecast|schedule|result|score|release|latest news|what['’]?s happening|who won|what time|what day|when does|where is|how much is)\b",
        r"\b(what['’]?s the latest|what['’]?s happening|recent updates|up to date|today['’]?s|current status)\b"
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


def _fetch_web_search_results(query, limit=4):
    if not query:
        return []
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    request = urllib.request.Request(
        search_url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            html_text = response.read().decode("utf-8", "ignore")
    except Exception:
        return []

    results = []
    for match in re.finditer(r'<a rel="nofollow" class="result__a" href="(.*?)"(.*?)>(.*?)</a>', html_text, flags=re.S):
        href = html.unescape(match.group(1) or "")
        title = re.sub(r"<.*?\>", "", match.group(3) or "")
        title = html.unescape(re.sub(r"\s+", " ", title)).strip()
        if href and title:
            results.append({"title": title, "url": href})
        if len(results) >= limit:
            break
    return results


def _build_live_search_context(user_message):
    if not _needs_live_web_search(user_message):
        return ""
    query = user_message.strip()
    results = _fetch_web_search_results(query, limit=4)
    if not results:
        return ""
    context_lines = ["Live web context:"]
    for index, item in enumerate(results, 1):
        context_lines.append(f"{index}. {item['title']} - {item['url']}")
    return "\n".join(context_lines)


def _extract_text_from_file(file_path, filename):
    if not file_path.exists():
        return ''
    if file_path.stat().st_size <= 0:
        return ''

    ext = Path(filename or '').suffix.lower()
    if ext == '.pdf':
        if PyPDF2 is None:
            return ''
        try:
            reader = PyPDF2.PdfReader(file_path)
            text_parts = []
            for page in reader.pages:
                text_parts.append(page.extract_text() or '')
            return '\n\n'.join(text_parts)
        except Exception:
            return ''
    if ext in {'.docx', '.doc'}:
        if DocxDocument is None:
            return ''
        try:
            document = DocxDocument(file_path)
            return '\n'.join(paragraph.text for paragraph in document.paragraphs if paragraph.text)
        except Exception:
            return ''
    if ext == '.txt':
        try:
            return file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return ''
    if ext == '.csv':
        try:
            if pd is not None:
                df = pd.read_csv(file_path)
                return df.to_string(index=False)
            return file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return ''
    if ext in {'.xlsx', '.xls'}:
        try:
            if pd is not None:
                df = pd.read_excel(file_path)
                return df.to_string(index=False)
            return ''
        except Exception:
            return ''
    if ext in {'.pptx', '.ppt'}:
        if Presentation is None:
            return ''
        try:
            prs = Presentation(file_path)
            text_parts = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, 'text'):
                        text = shape.text.strip()
                        if text:
                            text_parts.append(text)
            return '\n'.join(text_parts)
        except Exception:
            return ''
    if ext in {'.png', '.jpg', '.jpeg', '.webp'}:
        if Image is None or pytesseract is None:
            return ''
        try:
            image = Image.open(file_path)
            return pytesseract.image_to_string(image)
        except Exception:
            return ''
    return ''


def _get_session_id():
    payload = request.get_json(silent=True) or {}
    if isinstance(payload, dict):
        session_id = payload.get("session_id") or request.headers.get("X-Session-Id") or request.headers.get("X-User-Id")
        if session_id:
            return str(session_id)
    return request.args.get("session_id") or request.headers.get("X-Session-Id") or request.headers.get("X-User-Id") or "anonymous"


def _get_user_email():
    payload = request.get_json(silent=True) or {}
    if isinstance(payload, dict) and payload.get("user_email"):
        return str(payload.get("user_email"))
    return request.headers.get("X-User-Email") or request.headers.get("X-Email") or request.args.get("user_email") or ""


def _get_user_id():
    payload = request.get_json(silent=True) or {}
    if isinstance(payload, dict) and payload.get("user_id"):
        return str(payload.get("user_id"))
    return request.headers.get("X-User-Id") or request.args.get("user_id") or ""


def _get_user_scope():
    return {
        "user_id": _get_user_id(),
        "user_email": _get_user_email(),
        "session_id": _get_session_id(),
    }


def _request_supabase(method, path, payload=None, params=None):
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured")

    url = f"{SUPABASE_URL}/rest/v1{path}"
    if params:
        separator = '&' if '?' in url else '?'
        query = urllib.parse.urlencode(params, doseq=True)
        url = f"{url}{separator}{query}"

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            if not body:
                return []
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"Supabase request failed: {exc.code} {body}") from exc


@app.route("/")
def home():
    return "MI AI Running 🚀"


@app.route("/api/conversations", methods=["GET", "POST"])
def conversations():
    session_id = _get_session_id()
    scope = _get_user_scope()

    if request.method == "GET":
        try:
            params = {"order": "created_at.desc"}
            if scope.get("user_id"):
                params["user_id"] = f"eq.{scope['user_id']}"
            elif session_id and session_id != "anonymous":
                params["session_id"] = f"eq.{session_id}"
            rows = _request_supabase("GET", "/conversations", params=params)
            conversations_list = []
            for row in rows or []:
                conversations_list.append({
                    "id": row.get("id"),
                    "title": row.get("title", "New chat"),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at") or row.get("created_at"),
                    "message_count": row.get("message_count") or 0,
                    "last_preview": row.get("last_preview") or "",
                })
            return jsonify({"conversations": conversations_list})
        except Exception as exc:
            store = _load_local_store()
            return jsonify({"conversations": store.get("conversations", []), "warning": str(exc)})

    payload = request.get_json(silent=True) or {}
    title = payload.get("title", "New chat")
    session_id = payload.get("session_id") or session_id or "anonymous"
    user_email = scope.get("user_email") or ""
    user_id = scope.get("user_id") or session_id

    try:
        row = _request_supabase("POST", "/conversations", payload={
            "title": title,
            "session_id": session_id,
            "user_id": user_id,
            "user_email": user_email,
        })
        if isinstance(row, list) and row:
            row = row[0]
        return jsonify({"conversation": row})
    except Exception as exc:
        store = _load_local_store()
        conversation = {
            "id": f"chat_{len(store.get('conversations', [])) + 1}",
            "title": title,
            "session_id": session_id,
            "user_id": user_id,
            "user_email": user_email,
        }
        store.setdefault("conversations", []).append(conversation)
        _save_local_store(store)
        return jsonify({"conversation": conversation, "warning": str(exc)})


@app.route("/api/conversations/<conversation_id>", methods=["PATCH", "DELETE"])
def conversation_detail(conversation_id):
    scope = _get_user_scope()
    user_id = scope.get("user_id")
    session_id = scope.get("session_id")

    if not user_id and session_id == "anonymous":
        return jsonify({"error": "Authentication required"}), 401

    try:
        existing_rows = _request_supabase("GET", f"/conversations?id=eq.{conversation_id}", params={"select": "id,user_id,session_id"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    existing = (existing_rows or [{}])[0]
    if not existing:
        return jsonify({"error": "Conversation not found"}), 404

    if user_id and existing.get("user_id") and existing.get("user_id") != user_id:
        return jsonify({"error": "Forbidden"}), 403

    if request.method == "PATCH":
        payload = request.get_json(silent=True) or {}
        patch_payload = {}

        if "title" in payload:
            patch_payload["title"] = payload.get("title")
        if "updated_at" in payload:
            patch_payload["updated_at"] = payload.get("updated_at")
        if "last_preview" in payload:
            patch_payload["last_preview"] = payload.get("last_preview")
        if "message_count" in payload:
            patch_payload["message_count"] = payload.get("message_count")

        if not patch_payload:
            return jsonify({"error": "No valid fields provided"}), 400

        try:
            updated = _request_supabase("PATCH", f"/conversations?id=eq.{conversation_id}", payload=patch_payload)
            return jsonify({"conversation": updated})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    try:
        _request_supabase("DELETE", f"/conversations?id=eq.{conversation_id}")
        return jsonify({"deleted": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    safe_name = Path(filename).name
    file_path = UPLOAD_DIR / safe_name
    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404
    return send_from_directory(str(UPLOAD_DIR), safe_name, as_attachment=False)


@app.route("/api/upload", methods=["POST"])
def upload_file():
    scope = _get_user_scope()
    user_id = scope.get("user_id") or scope.get("session_id") or "anonymous"
    user_email = scope.get("user_email") or ""
    conversation_id = request.form.get("conversation_id")
    message_id = request.form.get("message_id")

    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400

    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "file is required"}), 400

    filename = uploaded.filename or "upload"
    if not filename.strip():
        return jsonify({"error": "file name is invalid"}), 400

    if not _allowed_file_type(filename, uploaded.mimetype):
        return jsonify({"error": "Unsupported file type"}), 400

    try:
        uploaded.stream.seek(0, os.SEEK_END)
        size = uploaded.stream.tell()
        uploaded.stream.seek(0)
    except Exception:
        size = 0

    if size <= 0:
        return jsonify({"error": "File is empty"}), 400

    if size > 20 * 1024 * 1024:
        return jsonify({"error": "File too large"}), 400

    safe_name = _safe_file_name(filename)
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    storage_path = UPLOAD_DIR / unique_name

    try:
        uploaded.save(storage_path)
    except Exception:
        return jsonify({"error": "Unable to save uploaded file"}), 400

    try:
        extracted_text = _extract_text_from_file(storage_path, filename)
    except Exception:
        extracted_text = ''

    attachment = {
        "id": f"att_{uuid.uuid4().hex[:8]}",
        "conversation_id": conversation_id,
        "message_id": message_id or None,
        "user_id": user_id,
        "user_email": user_email,
        "file_name": filename,
        "stored_name": unique_name,
        "file_size": storage_path.stat().st_size,
        "file_type": uploaded.mimetype or Path(filename).suffix.lower(),
        "upload_time": __import__('datetime').datetime.utcnow().isoformat() + 'Z',
        "extracted_text": extracted_text,
        "storage_path": str(storage_path),
        "uploaded_file_url": f"/uploads/{unique_name}",
    }

    store = _load_local_store()
    store.setdefault("attachments", []).append(attachment)
    _save_local_store(store)

    return jsonify({"attachment": attachment})


@app.route("/api/conversations/<conversation_id>/attachments", methods=["GET"])
def conversation_attachments(conversation_id):
    store = _load_local_store()
    attachments = [attachment for attachment in store.get("attachments", []) if attachment.get("conversation_id") == conversation_id]
    return jsonify({"attachments": attachments})


@app.route("/api/messages", methods=["GET", "POST"])
def messages():
    session_id = _get_session_id()
    scope = _get_user_scope()

    if request.method == "GET":
        conversation_id = request.args.get("conversation_id")
        if not conversation_id:
            return jsonify({"messages": []})
        try:
            params = {"conversation_id": f"eq.{conversation_id}", "order": "created_at.asc"}
            if scope.get("user_id"):
                params["user_id"] = f"eq.{scope['user_id']}"
            elif session_id and session_id != "anonymous":
                params["session_id"] = f"eq.{session_id}"
            rows = _request_supabase("GET", "/messages", params=params)
            items = []
            for row in rows or []:
                items.append({
                    "id": row.get("id"),
                    "conversation_id": row.get("conversation_id"),
                    "role": row.get("role"),
                    "content": row.get("content"),
                    "attachment_id": row.get("attachment_id"),
                    "attachment_meta": row.get("attachment_meta"),
                    "created_at": row.get("created_at"),
                })
            return jsonify({"messages": items})
        except Exception as exc:
            store = _load_local_store()
            items = [item for item in store.get("messages", []) if item.get("conversation_id") == conversation_id]
            return jsonify({"messages": items, "warning": str(exc)})

    payload = request.get_json(silent=True) or {}
    conversation_id = payload.get("conversation_id")
    content = payload.get("content", "")
    role = payload.get("role", "ai")
    session_id = payload.get("session_id") or session_id or "anonymous"
    user_email = scope.get("user_email") or ""
    user_id = scope.get("user_id") or session_id
    attachment_id = payload.get("attachment_id")
    attachment_meta = payload.get("attachment_meta")

    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400

    try:
        message_payload = {
            "conversation_id": conversation_id,
            "session_id": session_id,
            "user_id": user_id,
            "user_email": user_email,
            "role": role,
            "content": content,
        }
        if attachment_id is not None:
            message_payload["attachment_id"] = attachment_id
        if attachment_meta is not None:
            message_payload["attachment_meta"] = attachment_meta
        row = _request_supabase("POST", "/messages", payload=message_payload)
        if isinstance(row, list) and row:
            row = row[0]
        return jsonify({"message": row})
    except Exception as exc:
        store = _load_local_store()
        message = {
            "id": f"msg_{len(store.get('messages', [])) + 1}",
            "conversation_id": conversation_id,
            "session_id": session_id,
            "user_id": user_id,
            "user_email": user_email,
            "role": role,
            "content": content,
        }
        if attachment_id is not None:
            message["attachment_id"] = attachment_id
        if attachment_meta is not None:
            message["attachment_meta"] = attachment_meta
        store.setdefault("messages", []).append(message)
        _save_local_store(store)
        return jsonify({"message": message, "warning": str(exc)})


@app.route("/api/messages/<message_id>", methods=["PATCH"])
def message_detail(message_id):
    payload = request.get_json(silent=True) or {}
    patch_payload = {}
    if "attachment_id" in payload:
        patch_payload["attachment_id"] = payload.get("attachment_id")
    if "attachment_meta" in payload:
        patch_payload["attachment_meta"] = payload.get("attachment_meta")
    if not patch_payload:
        return jsonify({"error": "No valid fields provided"}), 400

    try:
        updated = _request_supabase("PATCH", f"/messages?id=eq.{message_id}", payload=patch_payload)
        if isinstance(updated, list) and updated:
            updated = updated[0]
        return jsonify({"message": updated})
    except Exception as exc:
        store = _load_local_store()
        for message in store.get("messages", []):
            if message.get("id") == message_id:
                if "attachment_id" in payload:
                    message["attachment_id"] = payload.get("attachment_id")
                if "attachment_meta" in payload:
                    message["attachment_meta"] = payload.get("attachment_meta")
                break
        _save_local_store(store)
        return jsonify({"message": {"id": message_id, **patch_payload}, "warning": str(exc)})



@app.route("/chat", methods=["POST"])
def chat():

    try:

        data = request.get_json()
        user_message = data.get("message","")
        history = data.get("history") or []
        attachment_ids = data.get("attachment_ids") or []
        attachment_id = data.get("attachment_id")

        if not user_message:
            return jsonify({
                "reply":"Please type a message."
            })


        attachment_context = ""
        attachment_refs = []
        if attachment_ids:
            attachment_refs = [item for item in attachment_ids if item]
        elif attachment_id:
            attachment_refs = [attachment_id]

        if attachment_refs:
            store = _load_local_store()
            matched = []
            for attachment in store.get("attachments", []):
                if attachment.get("id") in attachment_refs:
                    matched.append(attachment)
            if matched:
                attachment_context_parts = []
                for attachment in matched:
                    attachment_context_parts.append(
                        f"\n\nAttached file: {attachment.get('file_name')}\nFile type: {attachment.get('file_type')}\nStorage path: {attachment.get('storage_path') or ''}\nExtracted content:\n{attachment.get('extracted_text') or ''}"
                    )
                attachment_context = "".join(attachment_context_parts)

        messages_payload = [
            {
                "role": "system",
                "content": """

You are MI AI.

Creator:
M.I. Muhammadh

Age of creater: 17 years old

Ambition of creater: Derector of Flight Operations at SpaceX


IMPORTANT:
1. Answer the user's question correctly.
2. Do not invent facts.
3. If you don't know something, say you don't know.
4. Think before answering.
5. Give useful explanations.
6. Be fast and direct.
7. mi ai is an AI assistant created by M.I. Muhammadh.
8. MI AI is must analize the user's question and give the best possible answer.
9. The email of MI AI customer support is miai.customerservice@gmail.com
10. If the user asks about an uploaded file, answer using the attached file content as the primary source of truth.
11. For images, documents, spreadsheets, slides, and PDFs, analyze the complete content and answer any question from it.
12. For multiple files, use the relevant one(s) that match the user's question.
LANGUAGE RULE:
- Detect the language of the user's latest message.
- Reply ONLY in that language.
- English message = English reply only.
- Sinhala message = Sinhala reply only.
- Never mix languages unless the user mixes first.
- Always reply in the same script as the user's message.
- Always Use 100% correct words and grammar in replies.
- If the user writes in Sinhala letters, reply using Sinhala letters (සිංහල අකුරු).
- If the user writes in Tamil letters, reply using Tamil letters (தமிழ் எழுத்துக்கள்).
- If the user writes in English, reply using English.       
- If user uses another language, reply in that language.
- Do not translate unless asked.    
- if user writes in Singlish (Roman Sinhala), reply using Sinhala letters (සිංහල අකුරු).
- Do not use Singlish when user writes Sinhala.
- Do not use Tanglish when user writes Tamil.
- Never mix languages unless the user mixes them first.
- If user ask any question in any language, MI AI must reply in the same language and script as the user's question.
- ALWAYS follow the above language rules.
You can help with:
- Coding
- Science
- Maths
- Technology
- General knowledge
- Explanations
- Writing
- speech
- Exam preparations
- Learning new topics
- Language translations
- Learning new languages
- Learning new skills
- Life advice
- Learning new hobbies
- Learning new things
- Learning new subjects
- Learning new technologies
- Learning new programming languages
- Learning new frameworks
- Learning new tools
- Basic to advanced level topics
- Creating content
- Debugging code
- Giving step by step solutions
- Giving detailed explanations
- Giving concise answers
- Giving simple answers
- Giving easy to understand answers
- Giving in depth answers
- Giving short answers
- Giving long answers
- Giving examples
- Giving code examples
- Giving real life examples
- Giving practical examples
- Giving theoretical examples
- Giving mathematical examples
- Giving scientific examples
- Giving historical examples
- Giving philosophical examples
- Giving detailed explanations with examples
- Giving concise explanations with examples
- Giving simple explanations with examples
- Genarating new images based on user prompts
- Genarating new text based on user prompts
- Genarating new code based on user prompts
- Genarating new content based on user prompts
- Gebarate image captions based on user prompts
- Genarating new ideas based on user prompts
- Genarating new concepts based on user prompts
- Genarating new solutions based on user prompts
- and much more.

Your style:
Helpful, really smart and friendly.
You are MI AI.

IMPORTANT:
1. Answer correctly.
2. Do not invent facts.
3. If you don't know, say you don't know.
4. Be fast and direct.
5. Do not mention MI AI in replies.
6. Your name is MI AI
7. Your creater is M.I. Muhammadh
8. Always Must give full and complete answers to the user's question.
9. Use emojis when useful and appropriate.
10. Always use emojis in end of your answers when useful and appropriate.dont use in middle of sentences.
11. You must use only one emojy in each sentence and only at the end of the sentence when useful and appropriate.
12. Always follow the above rules and instructions.

LANGUAGE RULE:
- Detect the user's language.
- Reply ONLY in that language.
- Sinhala message = Sinhala reply.
- English message = English reply.
- If user uses another language, reply in that language.
- Do not translate unless asked.
- Detect the user's language.
- Reply ONLY in the same language and script.
- Sinhala typed in Sinhala letters = reply using Sinhala letters (සිංහල අකුරු).
- Tamil typed in Tamil letters = reply using Tamil letters (தமிழ் எழுத்துக்கள்).
- English typed in English = reply using English.
- Do not use Singlish when user writes Sinhala.
- Do not use Tanglish when user writes Tamil.
- Never mix languages unless the user mixes them first.
LANGUAGE RULE:
- Detect the exact writing style of the user's message.
- Always reply using the same language AND same script.

Examples:
- User: "ඔයා කොහොමද?"
  Reply: "මම හොඳින් ඉන්නවා."

- User: "oya kohomada?"
  Reply: "mama hondin innawa."

- User: "How are you?"
  Reply: "I am doing well."

- User: "நீ எப்படி இருக்கிறாய்?"
  Reply: "நான் நன்றாக இருக்கிறேன்."
- Sinhala letters input = Sinhala letters output only.
- Singlish input = Singlish output only.
- English input = English output only.
- Tamil letters input = Tamil letters output only.
- Do not convert Sinhala letters into Singlish.
- Do not convert Singlish into Sinhala letters.
- Do not mix scripts.
LANGUAGE RULE:

- Detect the user's language.
- If the user message is Sinhala OR Singlish (Roman Sinhala),
  always reply using Sinhala Unicode letters.

Examples:

User: "mata udaw karanna"
Reply: "මම උදව් කරන්නම්."

User: "මට උදව් කරන්න"
Reply: "මම උදව් කරන්නම්."

- English message = English reply.
- Tamil message = Tamil reply.
- Never reply Singlish when the user is speaking Sinhala/Singlish.
- Convert Singlish Sinhala meaning into Sinhala Unicode.
- Keep Sinhala replies natural and readable.
- Do not mention this rule.

REPLY STYLE:
- Reply like ChatGPT.
- Keep answers concise.
- Do not write long essays unless user asks.
- Use simple explanations.
- Use bullet points when useful.
- Avoid unnecessary introductions.


You can help with:
- Coding
- Science
- Maths
- Technology
- General knowledge
- Writing
- Explanations
- Writing
- speech
- Exam preparations
- Learning new topics
- Language translations
- Learning new languages
- Learning new skills
- Life advice
- Learning new hobbies
- Learning new things
- Learning new subjects
- Learning new technologies
- Learning new programming languages
- Learning new frameworks
- Learning new tools
- Basic to advanced level topics
- Creating content
- Debugging code
- Giving step by step solutions
- Giving detailed explanations
- Giving concise answers
- Giving simple answers
- Giving easy to understand answers
- Giving in depth answers
- Giving short answers
- Giving long answers
- Giving examples
- Giving code examples
- Giving real life examples
- Giving practical examples
- Giving theoretical examples
- Giving mathematical examples
- Giving scientific examples
- Giving historical examples
- Giving philosophical examples
- Giving detailed explanations with examples
- Giving concise explanations with examples
- Giving simple explanations with examples
- Genarating new images based on user prompts
- Genarating new text based on user prompts
- Genarating new code based on user prompts
- Genarating new content based on user prompts
- Gebarate image captions based on user prompts
- Genarating new ideas based on user prompts
- Genarating new concepts based on user prompts
- Genarating new solutions based on user prompts
- and much more.
"""
            }
        ]

        for item in history:
            role = item.get("role")
            content = item.get("content") or ""
            if role in {"user", "assistant", "system"} and content:
                messages_payload.append({"role": role, "content": content})

        search_context = _build_live_search_context(user_message)
        if attachment_context:
            user_prompt = f"{user_message}\n\n[Uploaded file context]\n{attachment_context}"
        else:
            user_prompt = user_message

        if search_context:
            user_prompt = f"{user_prompt}\n\n{search_context}\n\nIf the search results do not clearly answer the question, state that you could not verify the latest information."

        messages_payload.append({"role": "user", "content": user_prompt})

        groq_client = _get_groq_client()
        if groq_client is None:
            return jsonify({
                "reply": "The Groq API key is not configured. Please set GROQ_API_KEY to enable chat replies."
            })

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages_payload,
        )


        answer=response.choices[0].message.content


        return jsonify({
            "reply":answer
        })


    except Exception as e:

        return jsonify({
            "reply":"MI AI Error: "+str(e)
        })




if __name__=="__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )