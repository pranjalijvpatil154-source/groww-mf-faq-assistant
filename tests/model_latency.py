"""Compare latency of candidate light models (small prompt)."""
import json
import os
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
key = os.getenv("LLM_API_KEY")

CANDIDATES = ["gemini-flash-lite-latest", "gemini-3.5-flash-lite",
              "gemini-3.1-flash-lite", "gemini-3.8-flash"]

for name in CANDIDATES:
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{name}:generateContent")
    body = {"contents": [{"parts": [{"text": "Reply with exactly: OK"}]}]}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
        dt = time.time() - t0
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        print(f"{name:28s} {dt:6.1f}s  -> {text[:20]!r}")
    except Exception as e:
        print(f"{name:28s} FAIL after {time.time()-t0:5.1f}s  ({type(e).__name__}: {str(e)[:80]})")
