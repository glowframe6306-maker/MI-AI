#!/usr/bin/env python3
"""
Fix mojibake UTF-8 corruption using binary replacement
This handles the exact byte sequences in the file
"""

import os
import sys

file_path = r'c:\Users\Administrator\MI-AI\frontend\index.html'

try:
    # Read as binary to see exact bytes
    with open(file_path, 'rb') as f:
        data = f.read()
    
    original_size = len(data)
    
    print(f"Original file size: {original_size} bytes")
    
    # Mojibake to UTF-8 emoji replacements
    #  The patterns in the file are UTF-8 mojibake (double-encoded)
    # Pattern: ðŸ'' (which is U+F0 U+9F for UTF-8 emoji + mojibake chars)
    
    replacements = [
        # Format: (bytes_to_find, bytes_to_replace_with)
        (b'\xc3\x90\xc2\xb0\xc3\x82\xc2\xa6\xc3\x82\xc2\xb8\xc3\x82\xc2\xa2\xc3\xa2\xe2\x80\x9a\xc2\xac\xc3\x2039\xc5\x22\xc3\x82\xc2\xa2\xc3\xa2\xe2\x80\x9a\xc2\xac\xc3\x2039\xc5\x22', b'\xf0\x9f\x91\x91'),  # Complex emoji
        (b'\xc3\x90\xc2\xb3\xc3\x82\xc2\xb3', b'\xf0\x9f\x93\x8c'),  # Folder emoji
        (b'\xc3\x90\xc2\xb3\xc2\xac', b'\xf0\x9f\x97\x91'),  # Trash emoji  
    ]
    
    # Simple single-byte mojibake patterns
    simple_replacements = [
        (b'\xc3\x90\xc2\xb3\xc2\x93', b'\xf0\x9f\x91\x91'),  # Crown
        (b'\xc3\x90\xc2\xb3\xc2\x93', b'\xf0\x9f\x91\x91'),  # Crown alt
    ]
    
    for old, new in replacements + simple_replacements:
        count = data.count(old)
        if count > 0:
            print(f"Found {count} instances of pattern")
            data = data.replace(old, new)
    
    # Write back
    with open(file_path, 'wb') as f:
        f.write(data)
    
    new_size = len(data)
    print(f"New file size: {new_size} bytes")
    print("✓ Done")
    
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
