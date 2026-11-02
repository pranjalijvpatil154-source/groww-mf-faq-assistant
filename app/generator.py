"""Step 8 — Grounded generation (Layer 4).

answer(question, chunks) -> {text, citation_url, last_updated, mode}

Modes:
  llm        — chat LLM under the v1.md contract (needs LLM_API_KEY in .env)
  extractive — zero-key fallback (W1 logic: find the exact fact asked inside
               the retrieved chunks; never computes or extrapolates)
  pointer    — fact not located at all: points at the official document hub
  REFUSE     — empty chunks / generator decided refusal (caller shows template)

LLM path fails softly: on any API error we fall back to extractive and mark
mode="llm-failed" — the UI never shows a stack trace (E8).
"""
import json
import os
import re
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).parent.parent
load_dotenv(BASE / ".env")          # local only; .env is git-ignored
PROMPT_V1 = (BASE / "app" / "prompts" / "v1.md").read_text(encoding="utf-8")

# latency-tested in tests/model_latency.py: 3.1-flash-lite ~1s, 3.8-flash ~90s+
GEMINI_MODELS = ["gemini-3.1-flash-lite", "gemini-flash-lite-latest"]

# W1 — intent -> the exact fact phrase to look for in the chunk text
INTENT_TERMS = {
    "expense ratio": r"expense\s+ratio|ter\b",
    "exit load": r"exit\s+load",
    "lock-in": r"lock[\s-]?in",
    "minimum sip": r"minimum\s*(?:sip|amount|investment)|amount required|invest in mutual funds",
    "benchmark": r"benchmark",
    "riskometer": r"riskometer|risk\s+(?:level|ometer)",
    "statement": r"statement|capital[\s-]?gains|cas\b",
    "grievance": r"grievance|complaint|redressal",
    "kyc": r"\bkyc\b|know your customer",
    "document": r"\.pdf\b|kim\b|sid\b|factsheet|fact sheet",
}
GENERICS = (r"what\s+is\s+(?:a|an)?\s*mutual\s+fund",)

MAX_FACT_SENTENCES = 3


def _env_llm() -> tuple[str | None, str | None]:
    key = os.getenv("LLM_API_KEY", "").strip()
    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    return (key or None), provider


def _call_llm(provider: str, key: str, question: str, chunks: list[dict]) -> str | None:
    corpus = "\n\n".join(
        f"[source {c['source_id']} url={c['url']} last_updated={c['last_updated']}]\n"
        f"{c['chunk']['text']}"
        for c in chunks)
    user = (f"QUESTION: {question}\n\nCHUNKS:\n{corpus}\n\n"
            "Answer under the system contract, or output exactly REFUSE.")
    for attempt in range(3):                      # transient-demand retry (E8)
        try:
            if provider == "gemini":
                last_err = None
                for model in GEMINI_MODELS:
                    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
                           f"{model}:generateContent?key={key}")
                    body = {"contents": [{"parts": [{"text": PROMPT_V1 + "\n\n" + user}]}],
                            "generationConfig": {"temperature": 0.1}}
                    req = urllib.request.Request(
                        url, data=json.dumps(body).encode(),
                        headers={"Content-Type": "application/json"})
                    try:
                        with urllib.request.urlopen(req, timeout=60) as resp:
                            data = json.loads(resp.read())
                        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    except Exception as e:
                        last_err = e
                        continue
                return None
            # openai-compatible
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps({"model": "gpt-4o-mini", "temperature": 0.1,
                                 "messages": [{"role": "system", "content": PROMPT_V1},
                                              {"role": "user", "content": user}]}).encode(),
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {key}"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            if attempt == 2:
                return None
            time.sleep(3)


def _intent_of(question: str) -> str | None:
    q = question.lower()
    for label, pattern in INTENT_TERMS.items():
        if re.search(pattern, q):
            return label
    for pattern in GENERICS:
        if re.search(pattern, q):
            return pattern        # generic educational question
    return None


def _sentences(text: str) -> list[str]:
    """Atomic units: sentences, with table rows kept whole."""
    sents = []
    for line in text.splitlines():
        if "|" in line:
            sents.append(line.strip())
            continue
        sents.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip())
    return sents


def _extractive(question: str, chunks: list[dict]) -> dict:
    """Zero-key W1 fallback: verbatim fact sentences from a retrieved chunk."""
    intent = _intent_of(question)
    if intent:
        for c in sorted(chunks, key=lambda c: -c["score"]):
            text = c["chunk"]["text"]
            pattern = intent if intent.startswith(r"what") else INTENT_TERMS[intent]
            hits = [s for s in _sentences(text) if re.search(pattern, s, re.I)]
            if hits:
                return {"text": " ".join(hits[:MAX_FACT_SENTENCES]),
                        "citation_url": c["url"],
                        "last_updated": c["last_updated"],
                        "mode": "extractive"}
    # fact not found in any retrieved chunk -> honest pointer at official docs
    top = max(chunks, key=lambda c: c["score"])
    return {"text": "I can't locate this exact fact in my approved sources "
                    "(they live inside the official scheme documents). "
                    "The official document page for this is listed here.",
            "citation_url": top["url"],
            "last_updated": top["last_updated"],
            "mode": "pointer"}


def answer(question: str, chunks: list[dict]) -> dict:
    """Main entry. chunks = retriever OK-verdict chunk list."""
    if not chunks:
        return {"text": None, "mode": "REFUSE"}
    key, provider = _env_llm()
    if key:
        out = _call_llm(provider, key, question, chunks)
        if out:
            out = out.split("Last updated from sources:")[0].strip()
            if "REFUSE" not in out:
                urls = {c["url"].rstrip("/"): c for c in chunks}
                m = re.search(r"Source:\s*(\S+)", out)
                cite = (m.group(1).rstrip("/") if m else list(urls)[0])
                if cite not in urls:                 # citation must be allow-listed
                    cite = list(urls)[0]
                meta = urls[cite]
                # T13: deterministically trim LLM verbosity to <= 3 sentences
                sents = [s for s in re.split(r"(?<=[.!?])\s+", out) if s.strip()]
                body = " ".join(sents[:3]).strip()
                # drop the raw 'Source: ...' line (the UI renders the citation)
                body = re.sub(r"Source:\s*\S+\s*$", "", body,
                              flags=re.I).strip()
                return {"text": body, "citation_url": cite,
                        "last_updated": meta["last_updated"], "mode": "llm"}
            # LLM itself refused -> honest pointer to the official document page
            top = max(chunks, key=lambda c: c["score"])
            return {"text": "I can't locate this exact fact in my approved "
                            "sources (they live inside the official scheme "
                            "documents). The official document page for this "
                            "is listed here.",
                    "citation_url": top["url"],
                    "last_updated": top["last_updated"], "mode": "pointer"}
        return {**_extractive(question, chunks), "mode": "llm-failed"}
    return _extractive(question, chunks)
