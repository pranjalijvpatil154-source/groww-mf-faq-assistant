"""Step 9 — Guardrails (Layers 2 & 5 in ARCHITECTURE.md).

Input side:  check_input(question) -> verdict
Output side: check_output(text, citation_url, last_updated, approved_urls)

Input verdicts:
  PII_BLOCK | ADVICE_BLOCK | PERFORMANCE_BLOCK | OOS_BLOCK | OK

Output checks (unbypassable, deterministic):
  O1 citation URL must be on the approved allow-list          (T12, FR1)
  O2 <= 3 fact sentences before the footer                    (T13, FR5)
  O3 'Last updated from sources: <date>' footer present       (T14, FR4)
  O4 no advice/comparison/returns phrasing in the final text  (FR8)

Any failure -> REFUSE (refusals.template), never a raw LLM draft.
"""
import re
from datetime import date

PII_PATTERNS = {
    "PAN": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    "AADHAAR": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "PHONE": re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)"),
    "OTP": re.compile(r"\botp\b|\bone[\s-]?time\s+(?:password|pin)\b", re.I),
}

ADVICE_PHRASES = ("should i", "buy or sell", "sell or buy", "should we",
                  "which is better", "best fund", "worth it",
                  "recommend", "swap helps")

PERFORMANCE_PHRASES = ("returns", "performance", "perform", "cagr", "apy",
                       "% return", "past returns", "yield")

OUT_OF_SCOPE_TOKENS = ("hdfc", "sbi mutual", "icici", "parag parikh", "axis",
                       "kotak", "nippon", "bitcoin", "crypto", "nifty",
                       "stock", "shares", "trading", "demat")

SPLIT_SENTENCES = re.compile(r"(?<=[.!?])\s+")
DATE_STAMP = re.compile(r"Last updated from sources: \d{4}-\d{2}-\d{2}")
FORBIDDEN_OUTPUT = re.compile(
    r"\b(recommend|I (?:suggest|advise)|best scheme|you should (?:buy|sell)|"
    r"\d+(\.\d+)?\s?% return)\b", re.I)


def check_input(question: str) -> str:
    q = question.lower()
    if any(p.search(question) for p in PII_PATTERNS.values()):
        return "PII_BLOCK"
    if any(p in q for p in OUT_OF_SCOPE_TOKENS):
        return "OOS_BLOCK"
    if any(p in q for p in ADVICE_PHRASES):
        return "ADVICE_BLOCK"
    if any(p in q for p in PERFORMANCE_PHRASES):
        return "PERFORMANCE_BLOCK"
    return "OK"


def check_output(text: str, citation_url: str, last_updated: str,
                 approved_urls: list[str]) -> tuple[bool, str]:
    """Deterministic Layer-5 gates. Returns (ok, reason)."""
    if not text:
        return False, "empty draft"

    def norm(u): return u.rstrip("/")
    if norm(citation_url) not in {norm(u) for u in approved_urls}:
        return False, "citation not on approved allow-list (T12)"

    body = text.split("Last updated from sources:", 1)[0].strip()
    sent_count = len([s for s in SPLIT_SENTENCES.split(body) if s.strip()])
    if sent_count > 3:
        return False, f"{sent_count} sentences exceeds the 3-sentence limit (T13)"

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(last_updated or "")):
        return False, "date stamp missing or malformed (T14)"

    if FORBIDDEN_OUTPUT.search(text):
        return False, "advice/comparative/returns phrasing detected (FR8)"
    return True, "ok"


def approved_urls_from_csv(csv_path) -> list[str]:
    import csv as _csv
    lines = [ln for ln in csv_path.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")]
    return [r["url"] for r in _csv.DictReader(lines)]
