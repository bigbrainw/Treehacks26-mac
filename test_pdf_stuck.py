#!/usr/bin/env python3
"""
Test: send a few "user stuck" requests for a specific PDF with page numbers.
Simulates user stuck on Neurable_Whitepaper.pdf at different pages.
Logs show app, file, page.

Usage:
  python test_pdf_stuck.py
  python test_pdf_stuck.py --url https://YOUR_NGROK.ngrok-free.app
  python test_pdf_stuck.py --count 3
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config

try:
    import requests
except ImportError:
    print("Error: pip install requests")
    sys.exit(1)

# Simulated context: user reading Neurable Whitepaper PDF
PDF_PATH = "/Users/elijah/neurofocus_complete_resources/signal_processing_methods/Neurable_Whitepaper.pdf"
PDF_NAME = "Neurable_Whitepaper.pdf"
APP_NAME = "Preview"


def make_context(page: int, total_pages: int = 42, duration_seconds: float = 15.0):
    """Build context dict for POST /eeg."""
    return {
        "app_name": APP_NAME,
        "window_title": f"{PDF_NAME} — Page {page} of {total_pages}",
        "context_type": "file",
        "context_id": f"{APP_NAME}::{PDF_PATH}",
        "reading_section": f"Page {page} of {total_pages}",
        "page_number": page,
        "file_path": PDF_PATH,
        "duration_seconds": duration_seconds,
        "mental_state": "stuck",
    }


def send_stuck_request(jetson_url: str, page: int, total_pages: int, count: int):
    """POST one stuck request to Jetson."""
    ctx = make_context(page, total_pages, duration_seconds=10.0 + count * 5)
    body = {
        "timestamp": time.time(),
        "streams": {"met": {"met": [True, 0.4, True, 0.5, 0.4, True, 0.5], "time": time.time()}},
        "context": ctx,
    }
    r = requests.post(
        jetson_url,
        json=body,
        headers={"Content-Type": "application/json", "ngrok-skip-browser-warning": "1"},
        timeout=15,
    )
    return r, ctx


def main():
    p = argparse.ArgumentParser(description="Test: send stuck requests for PDF with page numbers")
    p.add_argument("--url", default=None, help="Jetson base URL (default: from config)")
    p.add_argument("--count", type=int, default=3, help="Number of requests to send")
    p.add_argument("--pages", type=str, default="5,12,20", help="Page numbers to simulate (comma-separated)")
    args = p.parse_args()

    base = args.url or config.JETSON_BASE.rstrip("/")
    jetson_url = f"{base}/eeg"

    pages = [int(p.strip()) for p in args.pages.split(",")]
    total_pages = 42

    print("\n--- PDF Stuck Test ---")
    print(f"  File: {PDF_NAME}")
    print(f"  Path: {PDF_PATH}")
    print(f"  URL:  {jetson_url}")
    print(f"  Pages: {pages}")
    print()

    for i, page in enumerate(pages[: args.count]):
        r, ctx = send_stuck_request(jetson_url, page, total_pages, i)
        print(f"[{i + 1}] POST {jetson_url}")
        print(f"    App: {ctx['app_name']} | File: {ctx['window_title']} | Page: {ctx['page_number']} | {ctx['reading_section']}")
        print(f"    Response: {r.status_code}")
        if r.status_code == 200 and r.text:
            try:
                data = r.json()
                fb = data.get("feedback") or data.get("message")
                if fb:
                    print(f"    Feedback: {fb[:80]}...")
            except Exception:
                pass
        else:
            print(f"    Body: {r.text[:100]}...")
        print()

    print("Done.")


if __name__ == "__main__":
    main()
