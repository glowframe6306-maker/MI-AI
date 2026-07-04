from flask import Flask, request, jsonify, send_from_directory, session, redirect, make_response
from flask_cors import CORS
import os
import re
import uuid
import requests
import ssl
from datetime import datetime, timedelta
import secrets

import random
import smtplib

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    from supabase import create_client
except ImportError:
    create_client = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
IMAGES_DIR = os.path.join(BASE_DIR, "images")

app = Flask(
    __name__,
    static_folder=FRONTEND_DIR,
    template_folder=FRONTEND_DIR,
    static_url_path=""
)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=not bool(os.getenv('DEV_MODE', '').lower() in ['1', 'true', 'yes']),
)
CORS(app)

otp_storage = {}
login_tokens = {}
trusted_devices = {}
login_attempts = {}
OTP_EXPIRATION_MINUTES = 10
TRUSTED_DEVICE_EXPIRATION_DAYS = 99999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW_MINUTES = 15
conversations_store = {}
messages_store = {}

OTP_EMAIL_ADDRESS = os.getenv("OTP_EMAIL_ADDRESS", "glowframe6306@gmail.com").strip()
OTP_EMAIL_PASSWORD = os.getenv("OTP_EMAIL_PASSWORD", "ogsx qccn nkfp cbdk").replace(" ", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")

@app.route('/images/<path:filename>')
def images(filename):
    return send_from_directory(IMAGES_DIR, filename)

api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key) if Groq and api_key else None

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(supabase_url, supabase_key) if create_client and supabase_url and supabase_key else None


def get_client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def prune_old_attempts(key):
    now = datetime.utcnow()
    attempts = login_attempts.get(key, [])
    login_attempts[key] = [ts for ts in attempts if now - ts < timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)]
    return login_attempts[key]


def record_login_attempt(key):
    prune_old_attempts(key)
    login_attempts.setdefault(key, []).append(datetime.utcnow())


def is_rate_limited(key):
    attempts = prune_old_attempts(key)
    return len(attempts) >= RATE_LIMIT_MAX_ATTEMPTS


def create_secure_token():
    return secrets.token_urlsafe(32)


def store_login_token(user_id, email, device_info):
    token = create_secure_token()
    login_tokens[token] = {
        "user_id": user_id,
        "email": email,
        "device_info": device_info,
        "expires_at": (datetime.utcnow() + timedelta(minutes=OTP_EXPIRATION_MINUTES)).isoformat(),
        "used": False,
    }
    return token


def validate_login_token(token):
    entry = login_tokens.get(token)
    if not entry:
        return None
    expires_at = datetime.fromisoformat(entry["expires_at"])
    if datetime.utcnow() > expires_at or entry["used"]:
        login_tokens.pop(token, None)
        return None
    return entry


def create_trusted_device(user_id, email):
    device_token = create_secure_token()
    trusted_devices[device_token] = {
        "user_id": user_id,
        "email": email,
        "expires_at": (datetime.utcnow() + timedelta(days=TRUSTED_DEVICE_EXPIRATION_DAYS)).isoformat(),
    }
    return device_token


def validate_trusted_device(device_token, user_id):
    if not device_token:
        return False
    entry = trusted_devices.get(device_token)
    if not entry:
        return False
    expires_at = datetime.fromisoformat(entry["expires_at"])
    if datetime.utcnow() > expires_at:
        trusted_devices.pop(device_token, None)
        return False
    return entry.get("user_id") == user_id


def authenticate_user(email, password):
    if not supabase_url or not SUPABASE_ANON_KEY:
        return None, "Authentication service unavailable."
    try:
        auth_url = f"{supabase_url}/auth/v1/token?grant_type=password"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        response = requests.post(auth_url, json={"email": email, "password": password}, headers=headers, timeout=10)
        if response.status_code != 200:
            result = response.json() if response.headers.get("Content-Type", "").startswith("application/json") else {}
            return None, result.get("error_description") or result.get("error") or "Invalid credentials."
        payload = response.json()
        user_data = payload.get("user") or {}
        return {
            "user_id": user_data.get("id"),
            "email": user_data.get("email"),
            "token": payload.get("access_token"),
        }, None
    except Exception as exc:
        app.logger.error("Supabase authentication failed: %s", exc)
        return None, "Authentication service error."

@app.route("/")
def home():
    return app.send_static_file("index.html")

@app.route("/send-otp", methods=["POST"])
def send_otp():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({
            "success": False,
            "message": "Email is required."
        }), 400

    if not OTP_EMAIL_ADDRESS or not OTP_EMAIL_PASSWORD:
        app.logger.error("OTP email SMTP credentials are not configured.")
        return jsonify({
            "success": False,
            "message": "Email service is not configured."
        }), 500

    user_info = None
    if supabase:
        try:
            user_record = supabase.table("users").select("id").eq("email", email).limit(1).execute()
            user_data = getattr(user_record, "data", None) or []
            if user_data:
                user_info = user_data[0]
        except Exception as e:
            app.logger.error("Failed to look up user for OTP: %s", e)

    if not user_info:
        return jsonify({
            "success": False,
            "message": "No account found for that email."
        }), 404

    token = create_secure_token()
    expiration = datetime.utcnow() + timedelta(minutes=OTP_EXPIRATION_MINUTES)
    login_tokens[token] = {
        "user_id": user_info.get("id"),
        "email": email,
        "expires_at": expiration.isoformat(),
        "used": False,
    }

    verification_link = f"{request.url_root.rstrip('/')}/verify-login?token={token}"
    msg = MIMEMultipart()
    msg["From"] = OTP_EMAIL_ADDRESS
    msg["To"] = email
    msg["Subject"] = "MI AI Login Verification"

    body = f"""
Welcome to MI AI.

A login attempt was made from a new device or browser.

Click the link below to complete sign in:

{verification_link}

This link expires in {OTP_EXPIRATION_MINUTES} minutes and can be used only once.
"""

    msg.attach(MIMEText(body, "plain"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls(context=context)
            server.login(OTP_EMAIL_ADDRESS, OTP_EMAIL_PASSWORD)
            server.send_message(msg)

        return jsonify({
            "success": True,
            "message": "Verification email sent successfully.Please check your spam folder."
        })

    except Exception as e:
        app.logger.error("Failed to send verification email: %s", e)
        return jsonify({
            "success": False,
            "message": "Failed to send verification email. Please check email settings."
        }), 500


@app.route("/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    device_info = request.headers.get("User-Agent") or get_client_ip()

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required."}), 400

    if is_rate_limited(email):
        return jsonify({"success": False, "message": "Too many login attempts. Try again later."}), 429

    auth_result, auth_error = authenticate_user(email, password)
    if auth_error or not auth_result or not auth_result.get("user_id"):
        record_login_attempt(email)
        return jsonify({"success": False, "message": auth_error or "Invalid credentials."}), 401

    user_id = auth_result["user_id"]
    trusted_token = request.cookies.get("trusted_device")
    if trusted_token and validate_trusted_device(trusted_token, user_id):
        return jsonify({
            "success": True,
            "trusted": True,
            "user_id": user_id,
            "email": email,
            "access_token": auth_result.get("token")
        })

    token = store_login_token(user_id, email, device_info)
    verification_link = f"{request.url_root.rstrip('/')}/verify-login?token={token}"
    msg = MIMEMultipart()
    msg["From"] = OTP_EMAIL_ADDRESS
    msg["To"] = email
    msg["Subject"] = "MI AI Login Verification"

    body = f"""
Welcome to MI AI.

A login attempt was made from a new device or browser.

Click the link below to complete sign in:

{verification_link}

This link expires in {OTP_EXPIRATION_MINUTES} minutes and can be used only once.
"""

    msg.attach(MIMEText(body, "plain"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls(context=context)
            server.login(OTP_EMAIL_ADDRESS, OTP_EMAIL_PASSWORD)
            server.send_message(msg)

        return jsonify({
            "success": True,
            "verification_required": True,
            "message": "Verification email sent successfully. please check your spam folder."
        })

    except Exception as e:
        app.logger.error("Failed to send verification email: %s", e)
        return jsonify({
            "success": False,
            "message": "Failed to send verification email. Please check email settings."
        }), 500


@app.route("/verify-login", methods=["GET"])
def verify_login():
    token = (request.args.get("token") or "").strip()
    if not token:
        return redirect("/?verified=0")

    entry = validate_login_token(token)
    if not entry:
        return redirect("/?verified=0")

    entry["used"] = True
    device_token = create_trusted_device(entry["user_id"], entry["email"])
    response = make_response(redirect("/?verified=1"))
    response.set_cookie(
        "trusted_device",
        device_token,
        httponly=True,
        secure=app.config.get("SESSION_COOKIE_SECURE", False),
        samesite="Lax",
        max_age=TRUSTED_DEVICE_EXPIRATION_DAYS * 24 * 60 * 60,
        path="/"
    )
    return response


@app.route("/logout", methods=["POST"])
def api_logout():
    response = jsonify({"success": True})
    response.delete_cookie("trusted_device", path="/")
    return response


@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    otp = str(data.get("otp") or "").strip()

    if not email or not otp:
        return jsonify({
            "success": False,
            "message": "Email and OTP are required."
        }), 400

    entry = otp_storage.get(email)
    if not entry:
        return jsonify({
            "success": False,
            "message": "OTP is invalid or expired."
        }), 400

    expires_at = datetime.fromisoformat(entry["expires_at"])
    if datetime.utcnow() > expires_at:
        otp_storage.pop(email, None)
        return jsonify({
            "success": False,
            "message": "OTP has expired."
        }), 400

    if entry["otp"] != otp:
        return jsonify({
            "success": False,
            "message": "OTP is invalid."
        }), 400

    otp_storage.pop(email, None)
    return jsonify({
        "success": True,
        "message": "OTP verified successfully."
    })


@app.route("/api/auth/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}
    full_name = str(data.get("fullName") or "").strip()
    age_value = data.get("age")
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")

    if not full_name:
        return jsonify({"error": "Full Name cannot be empty."}), 400

    try:
        age = int(age_value)
    except (TypeError, ValueError):
        age = None

    if not isinstance(age, int) or age < 1:
        return jsonify({"error": "Age must be a valid number."}), 400

    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return jsonify({"error": "Please enter a valid email address."}), 400

    if not password:
        return jsonify({"error": "Password cannot be empty."}), 400

    if not supabase:
        return jsonify({"error": "Authentication service unavailable."}), 503

    try:
        existing = supabase.table("users").select("id").eq("email", email).limit(1).execute()
        existing_users = getattr(existing, "data", None) or []
        if existing_users:
            return jsonify({"error": "Already registered or registered from Google. Create a new password or Use your previous to sign in."}), 409
    except Exception as db_err:
        app.logger.error("Duplicate email lookup failed: %s", db_err)
        return jsonify({"error": "Server error while checking duplicate email."}), 500

    try:
        created = supabase.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": full_name,
                "age": age,
            },
        })
        created_user = getattr(created, "user", None)
        user_id = getattr(created_user, "id", None)
        if not user_id:
            if isinstance(created, dict):
                created_user = created.get("user") or {}
                user_id = created_user.get("id")

        if not user_id:
            return jsonify({"error": "Registration failed."}), 400

        supabase.table("users").upsert({
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "age": age,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }, on_conflict="id").execute()

        return jsonify({"ok": True})
    except Exception as exc:
        message = str(exc).lower()
        if "already" in message or "registered" in message or "exists" in message:
            return jsonify({"error": "Already registered. Please sign in."}), 409
        app.logger.error("Supabase registration failed: %s", exc)
        return jsonify({"error": "Registration failed."}), 400


@app.route("/supabase-config", methods=["GET"])
def supabase_config():
    supabase_url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")

    if not supabase_url or not supabase_anon_key:
        app.logger.error("Supabase public config is not configured.")
        return jsonify({
            "success": False,
            "message": "Supabase configuration is not available."
        }), 500

    return jsonify({
        "success": True,
        "supabaseUrl": supabase_url,
        "supabaseAnonKey": supabase_anon_key
    })


@app.route("/conversations", methods=["GET", "POST"])
def conversations():
    if request.method == "GET":
        session_id = request.args.get("session_id")
        conversations_list = []
        for conversation in conversations_store.values():
            if session_id and conversation.get("session_id") != session_id:
                continue
            conversations_list.append({
                "id": conversation["id"],
                "title": conversation.get("title") or "New chat",
                "session_id": conversation.get("session_id"),
                "created_at": conversation.get("created_at"),
                "updated_at": conversation.get("updated_at"),
                "pin": conversation.get("pin", False),
            })
        conversations_list.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return jsonify({"conversations": conversations_list})

    data = request.get_json(silent=True) or {}
    conversation_id = str(data.get("id") or uuid.uuid4())
    title = (data.get("title") or "New chat").strip() or "New chat"
    session_id = data.get("session_id") or str(uuid.uuid4())

    conversation = conversations_store.get(conversation_id)
    if not conversation:
        conversation = {
            "id": conversation_id,
            "title": title,
            "session_id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "pin": False,
        }
        conversations_store[conversation_id] = conversation
        messages_store[conversation_id] = []
    else:
        conversation["title"] = title
        conversation["session_id"] = session_id
        conversation["updated_at"] = datetime.utcnow().isoformat()

    return jsonify({"conversation": {
        "id": conversation["id"],
        "title": conversation.get("title") or "New chat",
        "session_id": conversation.get("session_id"),
        "created_at": conversation.get("created_at"),
        "updated_at": conversation.get("updated_at"),
        "pin": conversation.get("pin", False),
    }})


@app.route("/messages", methods=["GET", "POST"])
def messages():
    if request.method == "GET":
        conversation_id = request.args.get("conversation_id")
        if not conversation_id:
            return jsonify({"messages": []})

        messages_list = messages_store.get(conversation_id, [])
        return jsonify({"messages": [{
            "id": message["id"],
            "conversation_id": message.get("conversation_id"),
            "role": message.get("role"),
            "content": message.get("content"),
            "created_at": message.get("created_at"),
        } for message in messages_list]})

    data = request.get_json(silent=True) or {}
    conversation_id = data.get("conversation_id") or str(uuid.uuid4())
    content = (data.get("content") or "").strip()
    role = data.get("role") or "user"
    session_id = data.get("session_id") or str(uuid.uuid4())

    if not content:
        return jsonify({"error": "Content is required."}), 400

    if conversation_id not in conversations_store:
        conversations_store[conversation_id] = {
            "id": conversation_id,
            "title": "New chat",
            "session_id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "pin": False,
        }
        messages_store[conversation_id] = []

    message = {
        "id": str(uuid.uuid4()),
        "conversation_id": conversation_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "created_at": datetime.utcnow().isoformat(),
    }
    messages_store[conversation_id].append(message)
    conversations_store[conversation_id]["updated_at"] = datetime.utcnow().isoformat()

    return jsonify({
        "message": message,
        "conversation_id": conversation_id,
        "content": content,
    })


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(silent=True) or {}
        user_message = str(data.get("message", "") or "").strip()
        session_id = data.get("session_id") or str(uuid.uuid4())
        conversation_id = data.get("conversation_id")
        user_id = data.get("user_id")
        user_email = data.get("user_email")
        user_agent = request.headers.get("User-Agent")
        ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)

        if not user_message:
            return jsonify({"reply": "Please type a message."}), 400

        if not client:
            return jsonify({
                "reply": "SERVER UNAVAILABLE😔."
            })

        if not conversation_id:
            conversation_id = str(uuid.uuid4())

        if conversation_id not in conversations_store:
            conversations_store[conversation_id] = {
                "id": conversation_id,
                "title": None,
                "session_id": session_id,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "pin": False,
            }

        if conversation_id not in messages_store:
            messages_store[conversation_id] = []

        if supabase:
            if user_id or user_email:
                try:
                    supabase.table("users").upsert({
                        "id": user_id or user_email,
                        "email": user_email,
                    }).execute()
                except Exception as db_err:
                    app.logger.error("Supabase user upsert failed: %s", db_err)

            try:
                supabase.table("conversations").upsert({
                    "id": conversation_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "user_email": user_email,
                    "status": "active",
                    "title": None,
                }).execute()
            except Exception as db_err:
                app.logger.error("Supabase conversation upsert failed: %s", db_err)

            try:
                supabase.table("messages").insert({
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "user_email": user_email,
                    "role": "user",
                    "content": user_message,
                    "model": "llama-3.3-70b-versatile",
                    "token_usage": None,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                }).execute()
            except Exception as db_err:
                app.logger.error("Supabase user message insert failed: %s", db_err)

        history_messages = []
        if messages_store.get(conversation_id):
            history_messages = [
                {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                for msg in messages_store[conversation_id]
            ]
        elif supabase:
            try:
                history = supabase.table("messages") \
                    .select("role,content") \
                    .eq("conversation_id", conversation_id) \
                    .order("created_at") \
                    .execute()
                history_messages = [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in getattr(history, "data", [])
                ]
            except Exception as db_err:
                app.logger.error("Supabase history fetch failed: %s", db_err)

        messages_store[conversation_id].append({
            "role": "user",
            "content": user_message,
        })
        conversations_store[conversation_id]["updated_at"] = datetime.utcnow().isoformat()

        chat_messages = []

        chat_messages.append({
            "role": "system",
            "content": """You are MI AI.

Creator:
M.I. Muhammadh

Age of creater: 17 years old

Ambition of creater: Derector of Flight Operations at SpaceX

Customer service email addresses -  FOR CUSTOMER SUPPORT - miai.customerservice@gmail.com  ,  FOR OTHER REQUIRMENTS - teamofchatbot.miai@gmail.com
WHATSAPP NUMBER OF TEAM - 0756390621


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
10. Always use emojis in end of your answers when useful and appropriate.
11. You must use only one emoji in each sentence and only at the end of the sentence when useful and appropriate.
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
- Tamil typed in Tamil letters = reply using Tamil letters (தமிழ் எழුත்து).
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
"""
})

        for msg in history_messages:
            chat_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=chat_messages
        )

        answer = response.choices[0].message.content
        token_usage = None
        if hasattr(response, "usage") and response.usage:
            token_usage = response.usage.get("total_tokens") if isinstance(response.usage, dict) else None

        messages_store[conversation_id].append({
            "role": "assistant",
            "content": answer,
        })

        if supabase:
            try:
                supabase.table("messages").insert({
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "user_email": user_email,
                    "role": "assistant",
                    "content": answer,
                    "model": "llama-3.3-70b-versatile",
                    "token_usage": token_usage,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                }).execute()
            except Exception as db_err:
                app.logger.error("Supabase assistant message insert failed: %s", db_err)

        return jsonify({
            "reply": answer,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "user_id": user_id,
            "user_email": user_email,
            "token_usage": token_usage,
        })

    except Exception as e:
        app.logger.error("Chat request failed: %s", e)
        return jsonify({
            "reply":"The AI service is currently unavailable right now. Please try again in a moment."
        })




if __name__=="__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )

