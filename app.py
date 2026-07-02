from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import uuid
import requests

import random
import smtplib

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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
CORS(app)

otp_storage = {}

CORS(app)

otp_storage = {}

EMAIL = "glowframe6306@gmail.com"
PASSWORD = "ogsx qccn nkfp cbdk"

@app.route('/images/<path:filename>')
def images(filename):
    return send_from_directory(IMAGES_DIR, filename)

api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key) if Groq and api_key else None

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(supabase_url, supabase_key) if create_client and supabase_url and supabase_key else None

@app.route("/")
def home():
    return app.send_static_file("index.html")

@app.route("/send-otp", methods=["POST"])
def send_otp():

    data = request.get_json()

    email = data.get("email")

    if not email:
        return jsonify({
            "success": False,
            "message": "Email is required."
        }), 400

    otp = str(random.randint(10000000, 99999999))

    otp_storage[email] = otp

    msg = MIMEMultipart()

    msg["From"] = EMAIL
    msg["To"] = email
    msg["Subject"] = "MI AI Verification Code"

    body = f"""
Welcome to MI AI.

Your verification code is:

{otp}

This code expires in 5 minutes.
"""

    msg.attach(MIMEText(body, "plain"))

    try:

        server = smtplib.SMTP("smtp.gmail.com", 587)

        server.starttls()

        server.login(EMAIL, PASSWORD)

        server.send_message(msg)

        server.quit()

        return jsonify({
            "success": True
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500



@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json() or {}
        user_message = data.get("message", "")
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
                "reply": "The AI service is currently unavailable. Please add a valid GROQ_API_KEY to enable replies."
            }), 503

        if not conversation_id:
            conversation_id = str(uuid.uuid4())

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

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
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
                },

                {
                    "role": "user",
                    "content": user_message
                }

            ]

        )

        answer = response.choices[0].message.content
        token_usage = None
        if hasattr(response, "usage") and response.usage:
            token_usage = response.usage.get("total_tokens") if isinstance(response.usage, dict) else None

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

        return jsonify({
            "reply":"The AI service is currently unavailable right now. Please try again in a moment."
        })




if __name__=="__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )