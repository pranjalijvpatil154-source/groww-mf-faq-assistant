"""Step 8 smoke — run the ask() pipeline over the sample flows (headless)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.ui import ask  # noqa: E402

QUERIES = [
    "How do I download the capital gains statement?",
    "What is the minimum amount required to invest in mutual funds?",
    "How is my KYC validated?",
    "Where can I download the KIM of Groww Largecap Fund?",
    "What is the lock-in period of the ELSS scheme?",       # PDF-only fact
    "What is the exact expense ratio of Groww Largecap Fund?",  # fact value
    "Should I buy or sell Groww Largecap Fund?",            # advice
    "Tell me about HDFC mutual funds",                      # out of scope
    "My PAN is ABCDE1234F",                                 # PII
]

for q in QUERIES:
    a = ask(q)
    if a["kind"] == "answer":
        print(f"Q: {q}\nANSWER [{a['mode']}]\n  {a['text']}\n  {a['footer']} | {a['citation_url']}\n")
    else:
        print(f"Q: {q}\nREFUSAL [{a['verdict']}]\n  {a['text'][:150]}\n  link: {a['link']}\n")
