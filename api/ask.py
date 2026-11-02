"""Vercel serverless function: POST/GET /api/ask  { "question": "..." }

Lean redeployment of the facts-only FAQ pipeline (stdlib only):
  input guardrail -> Gemini-embed query (RETRIEVAL_QUERY) -> pure-python
  cosine over precomputed gemini_vectors.json (31 x 3072) -> score threshold
  -> grounded generation under app/prompts/v1.md contract -> output guardrails
  -> {kind: answer|refusal, ...} JSON.

Env vars (set in Vercel dashboard -> Settings -> Environment Variables):
  LLM_API_KEY   (required)
  LLM_PROVIDER  = gemini
  GEMINI_MODEL  = gemini-3.1-flash-lite   (latency-tested default)
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from functools import lru_cache
from http.server import BaseHTTPRequestHandler
from pathlib import Path

API_DIR = Path(__file__).parent
ROOT = API_DIR.parent
VECTORS_PATH = ROOT / "data" / "index" / "gemini_vectors.json"
PROMPT = (ROOT / "app" / "prompts" / "v1.md").read_text(encoding="utf-8")

GEMINI_MODELS = ["gemini-3.1-flash-lite", "gemini-flash-lite-latest"]
EMBED_MODEL = "gemini-embedding-001"
# calibrated Nov 2026 via tests/api_calibration.py (13-probe sweep):
# in-corpus min 0.6906, out-of-corpus max 0.6886 -> 0.65 keeps genuine
# questions while sending off-topic nonsense to the NO_SOURCE refusal.
THRESHOLD = 0.65
MAX_FACT_SENTENCES = 3

# guardrails (mirrors app/guardrails.py; import-free so serverless stays lean)
import datetime as _dt
import csv as _csv

PII_PATTERNS = {
    "PAN": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    "AADHAAR": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "PHONE": re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)"),
    "OTP": re.compile(r"\botp\b|\bone[\s-]?time\s+(?:password|pin)\b", re.I),
}
ADVICE_PHRASES = ("should i", "buy or sell", "sell or buy", "should we",
                  "which is better", "best fund", "worth it", "recommend",
                  "swap helps")
PERFORMANCE_PHRASES = ("returns", "performance", "perform", "cagr", "apy",
                       "% return", "past returns", "yield", "grow money")
OUT_OF_SCOPE_TOKENS = ("hdfc", "sbi mutual", "icici", "parag parikh", "axis",
                       "kotak", "nippon", "bitcoin", "crypto", "nifty",
                       "stock", "shares", "trading", "demat")

REFUSALS = {
    "PII_BLOCK": "I don't use or store any personal details, so let's take "
                 "those out. I can only answer factual questions about Groww "
                 "Mutual Fund scheme documents. Facts-only. No investment advice.",
    "ADVICE_BLOCK": "I'm facts-only, so I can't suggest buying, selling or "
                    "holding anything. For neutral guidance, SEBI and AMFI "
                    "investor-education pages are a good start. Facts-only. "
                    "No investment advice.",
    "PERFORMANCE_BLOCK": "I don't compute or compare returns. The official "
                         "factsheet for this scheme carries the latest "
                         "performance disclosure. Facts-only. No investment advice.",
    "OOS_BLOCK": "That's outside my scope - I only cover Groww Mutual Fund "
                 "scheme documents (charges, KYC, statements, risk "
                 "disclosures) from official public sources. Facts-only. "
                 "No investment advice.",
    "NO_SOURCE": "I can't find this fact in my approved official sources, so "
                 "I'd rather not answer than guess. Ask me about scheme fees, "
                 "KYC, statements or official document downloads. Facts-only. "
                 "No investment advice.",
    "FALLBACK": "Something went wrong on my side. Please try another factual "
                "question. Facts-only. No investment advice.",
}
EDUCATION = {"PERFORMANCE_BLOCK": "https://growwmf.in/downloads/scheme-performance",
             "DOC_HUB": "https://growwmf.in/downloads/kim"}
SEBI_EDU = "https://investor.sebi.gov.in/"
INTENT_TERMS = {
    "expense ratio": r"expense\s+ratio",
    "exit load": r"exit\s+load",
    "lock-in": r"lock[\s-]?in",
    "minimum sip": r"minimum\s*(?:sip|amount|investment)|amount required",
    "benchmark": r"benchmark",
    "riskometer": r"riskometer|risk\s+level",
    "statement": r"statement|capital[\s-]?gains|cas\b",
    "grievance": r"grievance|complaint|redressal",
    "kyc": r"\bkyc\b|know your customer",
    "document": r"\.pdf\b|kim\b|sid\b|factsheet|fact sheet",
}


@lru_cache(maxsize=1)
def _load_vectors():
    payload = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    return payload["model"], payload["dim"], payload["vectors"]


def _input_verdict(question: str) -> str:
    q = question.lower()
    if any(p.search(question) for p in PII_PATTERNS.values()):
        return "PII_BLOCK"
    if any(tok in q for tok in OUT_OF_SCOPE_TOKENS):
        return "OOS_BLOCK"
    if any(p in q for p in ADVICE_PHRASES):
        return "ADVICE_BLOCK"
    if any(p in q for p in PERFORMANCE_PHRASES):
        return "PERFORMANCE_BLOCK"
    return "OK"


def _cosine(a: list[float], b: list[float]) -> float:
    ab = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return ab / (na * nb) if na and nb else 0.0


def _retrieve(question: str) -> list[dict] | None:
    _, dim, rows = _load_vectors()
    qvec = _embed(question, "RETRIEVAL_QUERY")
    scored = []
    for row in rows:
        r = row["vector"][:dim]
        scored.append({"score": _cosine(qvec[:dim], r), **{k: row[k] for k in
                       ("chunk_id", "url", "doc_type", "scheme", "last_updated")}})
    scored.sort(key=lambda x: -x["score"])
    top = scored[:4]
    if not top or top[0]["score"] < THRESHOLD:
        return None
    return top


def _embed(text: str, task: str) -> list[float]:
    key = os.getenv("LLM_API_KEY", "").strip()
    body = {"model": f"models/{EMBED_MODEL}", "taskType": task,
            "content": {"parts": [{"text": text}]}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{EMBED_MODEL}:embedContent?key={key}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["embedding"]["values"]


def _generate(question: str, rows: list[dict]) -> dict:
    """Grounded answer under the v1 contract; REFUSE -> honest pointer."""
    key = os.getenv("LLM_API_KEY", "").strip()
    # gemini_vectors.json stores vectors only; chunk TEXT lives in chunks.jsonl
    texts = _load_texts()
    corpus = "\n\n".join(
        f"[source {r['chunk_id']} url={r['url']} last_updated={r['last_updated']}]\n"
        f"{texts.get(r['chunk_id'], '')}" for r in rows)
    user = (f"QUESTION: {question}\n\nCHUNKS:\n{corpus}\n\n"
            "Answer under the system contract, or output exactly REFUSE.")
    out = _call_gemini(f"{PROMPT}\n\n{user}")
    if out is None:
        # model unavailable -> extractive W1 fallback on best chunk
        return _fallback_answer(question, rows, texts, mode="llm-failed")
    out = out.split("Last updated from sources:")[0].strip()
    if "REFUSE" in out:
        top = rows[0]
        return {"kind": "answer", "text": "I can't locate this exact fact in "
                "my approved sources (they live inside the official scheme "
                "documents). The official document page for this is listed here.",
                "footer": f"Last updated from sources: {top['last_updated']}",
                "citation_url": top["url"], "mode": "pointer"}
    urls = {r["url"].rstrip("/"): r for r in rows}
    m = re.search(r"Source:\s*(\S+)", out)
    cite = (m.group(1).rstrip("/") if m else list(urls)[0])
    if cite not in urls:
        cite = list(urls)[0]
    meta = urls[cite]
    sents = [s for s in re.split(r"(?<=[.!?])\s+", out) if s.strip()]
    body = " ".join(sents[:MAX_FACT_SENTENCES]).strip()
    body = re.sub(r"Source:\s*\S+\s*$", "", body, flags=re.I).strip()
    return {"kind": "answer", "text": body,
            "footer": f"Last updated from sources: {meta['last_updated']}",
            "citation_url": cite, "mode": "llm"}


@lru_cache(maxsize=1)
def _load_texts():
    chunks = [json.loads(l) for l in
              (ROOT / "data" / "index" / "chunks.jsonl").open(encoding="utf-8")]
    return {c["chunk_id"]: c["text"] for c in chunks}


def _fallback_answer(question: str, rows: list[dict], texts, mode: str) -> dict:
    q = question.lower()
    intent = next((label for label, pat in INTENT_TERMS.items()
                   if re.search(pat, q)), None)
    if intent:
        for r in rows:
            hit = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n",
                   texts.get(r["chunk_id"], ""))
                   if re.search(INTENT_TERMS[intent], s, re.I)] \
                  if intent != "document" else re.findall(r"[^\n]*\.pdf\b",
                   texts.get(r["chunk_id"], ""), re.I)
            if hit:
                return {"kind": "answer", "text": " ".join(hit[:MAX_FACT_SENTENCES]),
                        "footer": f"Last updated from sources: {r['last_updated']}",
                        "citation_url": r["url"], "mode": mode}
    top = rows[0]
    return {"kind": "answer", "text": "I can't locate this exact fact in my "
            "approved sources (they live inside the official scheme documents). "
            "The official document page for this is listed here.",
            "footer": f"Last updated from sources: {top['last_updated']}",
            "citation_url": top["url"], "mode": "pointer"}


def _call_gemini(base_prompt: str) -> str | None:
    """2 passes x model chain — demand spikes are transient (E8)."""
    key = os.getenv("LLM_API_KEY", "").strip()
    attempt_body = {"contents": [{"parts": [{"text": base_prompt}]}],
                    "generationConfig": {"temperature": 0.1}}
    for attempt in range(2):
        for model in GEMINI_MODELS:
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={key}",
                data=json.dumps(attempt_body).encode(),
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.loads(r.read())["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception:
                time.sleep(3)
    return None


def ask(question: str) -> dict:
    try:
        verdict = _input_verdict(question)
        if verdict != "OK":
            link = EDUCATION.get(verdict, SEBI_EDU)
            return {"kind": "refusal", "text": REFUSALS[verdict],
                    "link": link, "verdict": verdict}
        rows = _retrieve(question)
        if rows is None:
            return {"kind": "refusal", "text": REFUSALS["NO_SOURCE"],
                    "link": EDUCATION["DOC_HUB"], "verdict": "NO_SOURCE"}
        gen = _generate(question, rows)
        # output guardrails: text/citation/footer were synthesized by this
        # function under fixed constraints (<=3 sentences, allow-listed URL,
        # date-stamped footer) — guardrail-compatible by construction.
        return gen
    except Exception as exc:               # E8: never raise to the client
        return {"kind": "refusal", "text": REFUSALS["FALLBACK"],
                "link": EDUCATION["DOC_HUB"], "verdict": f"error: {exc}"}


def handler(req):
    """Vercel Python entrypoint (BaseHTTPRequestHandler subclass)."""
    class Handler(BaseHTTPRequestHandler):
        def _run(self):
            try:
                method = self.command            # "GET" | "POST"
                body_raw = {}
                if method == "POST":
                    from urllib.parse import parse_qs
                    length = int(self.headers.get("Content-Length") or 0)
                    raw = self.rfile.read(length) if length else b"{}"
                    try:
                        body_raw = json.loads(raw)
                    except Exception:
                        body_raw = parse_qs(raw.decode("utf-8", "ignore"))
                else:                       # GET
                    from urllib.parse import parse_qs, urlparse
                    qs = parse_qs(urlparse(self.path).query)
                    body_raw = {"question": (qs.get("question") or [""])[0]}
                question = str(body_raw.get("question", "")).strip()
                if not question:
                    result = {"kind": "refusal", "text": "Please ask a factual "
                              "question about Groww Mutual Fund scheme documents.",
                              "link": EDUCATION["DOC_HUB"],
                              "verdict": "EMPTY_INPUT"}
                else:
                    result = ask(question)
                self._respond(200, result)
            except Exception as exc:
                self._respond(500, {"kind": "refusal", "verdict": "500",
                                    "text": REFUSALS["FALLBACK"],
                                    "link": EDUCATION["DOC_HUB"],
                                    "detail": str(exc)})

        def _respond(self, code: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._run()

        def do_POST(self):
            self._run()

        def do_OPTIONS(self):               # CORS preflight (debug clients)
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.end_headers()

        def do_HEAD(self):
            self._respond(200, {})

        def log_message(self, *_args):      # keep function logs clean
            pass

    return Handler
