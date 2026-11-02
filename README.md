# Groww MF Facts-Only FAQ Assistant

A retrieval-augmented (RAG) chat assistant that answers **factual questions about
Groww Mutual Fund scheme documents** — charges, KYC, statements, risk disclosures —
using **official public sources only**, with one allow-listed citation per answer.
It never gives investment advice, never comments on returns, and never stores or
echoes personal data.

> **Facts-only. No investment advice.**

**Live demo:** https://groww-mf-faq-assistant-s72f.vercel.app

---

## Scope

| Item | Value |
|---|---|
| **AMC** | Groww Mutual Fund (Groww Asset Management Company) |
| **Scheme categories** (3–5, one per category, per PRD) | 1. Large-cap (active) · 2. Flexi-cap (active) · 3. ELSS / tax-saver (3-year lock-in) · 4. optional index fund as a passive comparison |
| **Corpus** | 15 approved public URLs (AMC / SEBI / AMFI) — `ingest/source_list.csv` |
| **Out of scope** | other AMCs, returns/performance opinions, personal data, anything not on approved pages |

## What it does

| | |
|---|---|
| ✅ Answers factual questions | from 15 approved official URLs (AMC / SEBI / AMFI) |
| ✅ Cites exactly one source | from the approved allow-list, with a "last updated" date |
| ✅ Grounded generation | ≤ 3 sentences, LLM must refuse anything not in the retrieved chunks |
| ✅ Hard guardrails | PII (PAN/Aadhaar/email/phone/OTP), advice requests, performance questions, out-of-scope topics → deterministic, unbypassable refusals |
| ✅ Honest gap handling | facts that live only inside scheme PDFs (exit load %, min SIP ₹) → polite pointer to the official document page, never a guess |

## Architecture

```
question
  │
  ▼
[1] Input guardrails ──── PII / advice / performance / out-of-scope regex -> refusal
  ▼
[2] Retrieval ─────────── query embedded (gemini-embedding-001, RETRIEVAL_QUERY)
  │                        cosine vs 31 precomputed chunk vectors (RETRIEVAL_DOCUMENT)
  │                        threshold 0.65 (calibrated; tests/api_calibration.md)
  ▼
[3] Grounded generation ─ system contract (app/prompts/v1.md) + top-4 chunks
  │                        LLM: gemini-3.1-flash-lite (fallback chain)
  │                        LLM says REFUSE -> honest pointer answer
  ▼
[4] Output guardrails ─── citation allow-list (T12), ≤3 sentences (T13),
  │                        date-stamped footer (T14), advice-leak check (FR8)
  ▼
answer | refusal   (JSON: kind, text, footer/citation_url | link, verdict)
```

`requirements.txt` at the root is intentionally dependency-free: the Vercel
serverless function (`api/ask.py`) is **pure Python stdlib** — embed → cosine →
generate. No torch/FAISS on the server (they don't fit the runtime).

## Repository layout

```
DOC/                    problem statement, PRD, architecture, implementation plan
app/                    local Streamlit prototype (retriever, generator, guardrails, UI)
api/ask.py              Vercel serverless WSGI app (serves / and /api/ask)
index.html              deployed static frontend
ingest/                 scraper, loader, chunking, FAISS + Gemini embedding builders
data/index/             committed artifacts: chunks.jsonl, vectors, gemini_vectors.json
tests/                  T1-T15 guardrail suite, probe calibration, sample Q&A, smoke tests
```

## Local setup

```bash
pip install -r requirements-app.txt        # Streamlit prototype deps
copy .env.example .env                     # then put your real key in .env

# rebuild the corpus artifacts (optional — committed copies included):
py ingest/fetch_pages.py                   # scrape the 15 approved URLs
py ingest/load_docs.py                     # -> documents.jsonl
py ingest/build_index.py                   # chunk -> MiniLM vectors -> FAISS
py ingest/embed_gemini.py                  # ALSO re-embed for the serverless API

# run the local Streamlit UI:
py -m streamlit run app/ui.py --server.port 8501

# run tests:
py tests/test_guardrails.py                # T1-T15 guardrail suite
py tests/api_smoke.py                      # end-to-end pipeline smoke
```

Env vars (local `.env` / Vercel dashboard, never committed):

```
LLM_PROVIDER=gemini
LLM_API_KEY=<your key>
GEMINI_MODEL=gemini-3.1-flash-lite
```

## Deployment (Vercel)

1. Import the repo at vercel.com/new (framework preset **Other**).
2. Add the 3 environment variables above (Settings → Environment Variables).
3. Redeploy. Done — the function serves the UI at `/` and the FAQ API at `/api/ask`.

Byte budget: the function bundle excludes tests/docs via `vercel.json`
`excludeFiles` and contains no third-party packages.

## Evaluation results

- Guardrail suite **T1–T15: 21/21 pass** (`tests/test_guardrails.py`); exit bar
  (T1–T5, T12 at 100%) met.
- Sample Q&A: **8/8 correct** behavior incl. honest pointer answers
  (`tests/qa_samples.md`).
- Retrieval threshold calibration & probe sweep: `tests/api_calibration.md`.
- Embedding-space note: local MiniLM pilots run at threshold 0.35; the serverless
  API recalibrated to **0.65** in the Gemini embedding space (documented sweep).

## Sources of truth

15 approved URLs — see `ingest/source_list.csv` (AMC pages, SEBI investor
education + CAS page, AMFI "mutual funds sahi hai"). Deep numeric scheme facts
remain inside the official PDFs and are answered by pointer by design.

## Disclaimer

This assistant explains scheme-document facts. It is **not** investment advice,
doesn't compare funds, doesn't predict or report returns, and doesn't process
personal data. Please read the official scheme documents (SID / KIM / factsheet)
and consult a registered adviser before investing.
