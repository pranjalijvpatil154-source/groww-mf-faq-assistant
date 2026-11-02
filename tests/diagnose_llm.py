"""One-off diagnostic: test the configured provider/key (prints result, never the key)."""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
key = os.getenv("LLM_API_KEY", "").strip()
provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()

if not key:
    print("no key in .env")
    raise SystemExit

if provider == "gemini":
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-3.8-flash:generateContent?key={key}")
    body = {"contents": [{"parts": [{"text": "Reply with exactly: OK"}]}]}
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
else:
    url = "https://api.openai.com/v1/chat/completions"
    body = {"model": "gpt-4o-mini", "max_tokens": 10,
            "messages": [{"role": "user", "content": "Say OK"}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {key}"})

try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    if provider == "gemini":
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    else:
        text = data["choices"][0]["message"]["content"].strip()
    print(f"SUCCESS ({provider}):", text[:60])
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code} - {e.reason}")
    try:
        err = json.loads(e.read())
        msg = err.get("error", {})
        print("API says:", msg.get("status") or msg.get("type"), "-", str(msg.get("message", ""))[:300])
    except Exception:
        print("(unreadable body)")
except Exception as e:
    print(f"other error: {type(e).__name__}: {e}")
