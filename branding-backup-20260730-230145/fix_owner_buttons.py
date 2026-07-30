from pathlib import Path
import re

pattern = re.compile(r'<!--\s*MI_AI_CHIEF_OWNER_BUTTON\s*-->\s*<button\b[^>]*id="chiefOwnerBtn"[^>]*>.*?</script>', re.S | re.I)
replacement = '<!-- MI_AI_CHIEF_OWNER_BUTTON -->\n\n<button data-chief-owner-button="true" type="button" style="display:none;width:100%;margin-top:10px;padding:12px;border-radius:14px;background:linear-gradient(135deg,#D4AF37,#F7E27C);color:#111;font-weight:bold;cursor:pointer;border:none;">Chief Owner Permissions</button>'
script = '''\n<script>\n(function () {\n    "use strict";\n\n    function currentUser() {\n        try {\n            if (window.firebase?.auth) {\n                return window.firebase.auth().currentUser;\n            }\n\n            if (window.miFirebaseAuth) {\n                return window.miFirebaseAuth.currentUser;\n            }\n        } catch (error) {\n            console.warn("[MI AI] Chief owner lookup failed:", error);\n        }\n\n        return null;\n    }\n\n    function syncChiefOwnerButtons() {\n        const buttons = Array.from(document.querySelectorAll('[data-chief-owner-button="true"]'));\n        const user = currentUser();\n        const email = (user?.email || "").toLowerCase();\n\n        buttons.forEach(function (button) {\n            if (email === "teamofchatbot.miai@gmail.com") {\n                button.style.display = "block";\n                button.onclick = function () {\n                    location.href = "/chief-owner";\n                };\n            } else {\n                button.style.display = "none";\n                button.onclick = null;\n            }\n        });\n    }\n\n    if (document.readyState === "loading") {\n        document.addEventListener("DOMContentLoaded", syncChiefOwnerButtons, { once: true });\n    } else {\n        syncChiefOwnerButtons();\n    }\n\n    window.addEventListener("load", syncChiefOwnerButtons);\n    setTimeout(syncChiefOwnerButtons, 1000);\n})();\n</script>'''

for rel in ['frontend/index.html', 'index.html']:
    path = Path(rel)
    if not path.exists():
        continue
    text = path.read_text(encoding='utf-8')
    text, count = pattern.subn(replacement, text)
    if 'syncChiefOwnerButtons' not in text and '</body>' in text:
        text = text.replace('</body>', script + '\n</body>', 1)
    path.write_text(text, encoding='utf-8')
    print(f'{rel}: {count}')
