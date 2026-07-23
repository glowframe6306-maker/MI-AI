#!/usr/bin/env python3
"""
Fix mojibake/UTF-8 corruption in frontend/index.html
This script replaces all known corrupted emoji sequences with correct Unicode characters.
"""

import os

# Change to workspace directory
os.chdir(r'c:\Users\Administrator\MI-AI')

# Read the file
with open('frontend/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

print(f"Original file size: {len(content)} bytes")

# List of replacements: mojibake patterns to fix
replacements = {
    # Emoji mojibake
    'ðŸ''': '👑',
    'ðŸ"Œ': '📂',
    'ðŸ'¬': '🗑',
    'ðŸ"œ': '📄',
    'ðŸŽ§': '🎧',
    'ðŸ"' : '📌',
    'ðŸ'­' : '💭',
    'ðŸ"˜' : '📘',
    # Punctuation mojibake
    'âŒ': '✕',
    'â€™': ''',
    'â€œ': '"',
    'â€': '"',
    'â€"': '–',
    'â€¦': '…',
    'â€"': '—',
    'â€"': '-',
    'ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢': '•',
    # Complex double-encoded patterns
    'ÃƒÆ'Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã‹Å"ÃƒÂ¢Ã¢â€šÂ¬Ã‹Å"': '👑',
    'ÃƒÆ'Ã‚Â¢Ãƒâ€¦Ã¢â‚¬Å"ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢': '✕',
}

# Apply replacements
for mojibake, correct in replacements.items():
    count = content.count(mojibake)
    if count > 0:
        print(f"  Replacing '{mojibake}' ({count} instances) → '{correct}'")
        content = content.replace(mojibake, correct)

# Write back
with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"✓ Fixed mojibake corruption in index.html")
print(f"New file size: {len(content)} bytes")
