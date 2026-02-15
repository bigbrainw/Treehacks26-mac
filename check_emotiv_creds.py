#!/usr/bin/env python3
"""Verify Emotiv credentials load and provide -32021 troubleshooting steps."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config

cid = config.EMOTIV_CLIENT_ID
secret = config.EMOTIV_CLIENT_SECRET

print("Emotiv credentials check")
print("-" * 40)
print(f"  EMOTIV_CLIENT_ID:   {'loaded (' + str(len(cid)) + ' chars)' if cid else 'MISSING'}")
print(f"  EMOTIV_CLIENT_SECRET: {'loaded (' + str(len(secret)) + ' chars)' if secret else 'MISSING'}")

if not cid or not secret:
    print("\n  Add to .env: EMOTIV_CLIENT_ID=... and EMOTIV_CLIENT_SECRET=...")
    sys.exit(1)

print("\n  If you still get -32021 Invalid Client Credentials:")
print("  1. EMOTIV Launcher: log in, Settings -> Authorized Apps -> approve your app")
print("  2. Emotiv Developer: emotiv.com/developer -> verify Client ID/Secret match .env")
print("  3. Unpublished app: only the creator's EmotivID can use it")
print("\n  To run without headset: python app.py  (uses mock EEG)")
