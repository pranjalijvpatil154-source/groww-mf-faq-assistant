# Implementation Plan — Groww Mutual Fund Facts-Only FAQ Assistant (Simplified)

| Field | Value |
|---|---|
| Derived from | `DOC/ARCHITECTURE.md` ← `DOC/PRD.md` ← `DOC/ProblemStatment.txt` |
| Version | 2.0 (Simplified) |
| Date | 2026-11-01 |
| Product | Groww (locked for all milestones) |

**Build order:** Directory → Scraping → **Loading documents** → Chunking →
Embedding → Vector DB → Retrieval → UI → Edge cases & Guardrail tests.

---

## Step 1 — Create directory structure

Create this layout once:

```
newfolder/
├── DOC/                       # PM docs (already exists)
│   ├── ProblemStatment.txt
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   └── IMPLEMENTATION.md
├── ingest/                    # scrapers + index builder
│   ├── fetch_pages.py
│   ├── build_index.py
│   └── source_list.csv        # the approved 15–25 official URLs
├── app/                       # runtime
│   ├── ui.py                  # Streamlit UI
│   ├── retriever.py
│   ├── generator.py
│   ├── guardrails.py
│   └── refusals.py
├── data/
│   ├── raw/                   # cached fetched pages
│   └── index/                 # built vector DB files
├── tests/
│   ├── test_guardrails.py
│   └── qa_samples.md
├── .env.example               # LLM_API_KEY=  (never commit real key)
└── requirements.txt           # streamlit, requests, trafilatura,
                               # sentence-transformers, faiss-cpu, python-dotenv
```

**Done when:** all folders/files exist; `pip install -r requirements.txt`
works; no secrets committed.

---

## Step 2 — Scraping documents

**Goal:** download the official Groww AMC / SEBI / AMFI pages and extract
clean text. No blogs, no aggregators, no login pages.

**Tasks**
1. Fill `ingest/source_list.csv` — one row per official page (15–25 total):
   `source_id, url, publisher [AMC|SEBI|AMFI], doc_type [factsheet|KIM|SID|
   faq|fees|statement_guide|riskometer|education], scheme, last_updated`.
   - 3–5 Groww MF schemes (large-cap, flexi-cap, ELSS, optional index fund).
   - Include: per-scheme factsheet/KIM/SID/FAQ, AMC fee page, capital-gains
     statement download guide, riskometer/benchmark notes, one SEBI page,
     one AMFI investor-education page.
2. `fetch_pages.py`:
   - Fetch each URL, save raw HTML to `data/raw/<source_id>.html` (cached —
     never re-fetch in a loop).
   - Extract clean text with `trafilatura`.
   - **Keep tables**: convert HTML-table rows to text lines, e.g.
     `Direct Plan | Expense ratio: 0.50%` (expense ratios live in tables).
3. Verify before moving on: grep the text files for "expense ratio",
   "exit load", "minimum", "lock-in", "benchmark" — these facts must survive
   extraction.

**Done when:** all URLs fetched once, text extracted, fact keywords present,
CSV count is 15–25 and every row is an official page.

---

## Step 3 — Loading documents

**Goal:** read the extracted text files into one clean, validated,
in-memory document list — the single input for chunking.

**Tasks**
1. `ingest/load_docs.py`: load every `data/raw/<source_id>.txt` extracted by
   Step 2, keyed by `source_id` from `source_list.csv`.
2. Join each loaded document with its CSV metadata:
   `{source_id, url, publisher, doc_type, scheme, last_updated, text}`.
3. Validate per document:
   - non-empty text and reasonable length (min ~200 chars);
   - text is valid UTF-8 (fix mojibake / remove null bytes);
   - `source_id` in CSV and URL is on the approved list.
4. Clean up: strip repeated boilerplate (headers/footers, cookie banners),
   collapse blank lines, drop obvious junk pages.
5. Deduplicate: if a URL or near-identical text appears twice, keep one copy.
6. Write the result to `data/index/documents.jsonl` — one JSON object per
   official page. Chunking (Step 4) consumes this file; it never touches
   the raw HTML directory.

**Done when:** `documents.jsonl` has exactly one clean entry per approved
URL (15–25 total), each with full metadata, and the fact keywords verified
in Step 2 are still findable in the loaded text.

---

## Step 4 — Chunking

**Goal:** break cleaned text into small retrievable pieces.

**Tasks**
1. Chunk size: **300–500 tokens**, ~15% overlap between chunks.
2. Never split a fact sentence or table row across two chunks.
3. Attach metadata to every chunk:
   `{source_id, url, publisher, doc_type, scheme, last_updated, chunk_idx}`.
4. Save chunks to JSONL at `data/index/chunks.jsonl` (intermediate artifact,
   easy to debug).

**Done when:** every chunk carries its URL + scheme metadata; spot check
shows expense ratio / exit-load lines inside one chunk each.

---

## Step 5 — Embedding

**Goal:** convert chunks to vectors.

**Tasks**
1. Use `sentence-transformers` MiniLM (local model, no API needed).
2. Embed **every chunk** through the same embedder.
3. Also embed at query time with the **same** model — this consistency is
   critical; hard-code the model name in one place (`app/retriever.py`).
4. Log the embedder name + version into `data/index/manifest.json`.

**Done when:** every chunk row in JSONL gains a `vector`; manifest written.

---

## Step 6 — Storing data in vector DB

**Goal:** one local, zero-infra index.

**Tasks**
1. Store vectors + metadata in **FAISS (flat, cosine)** or **ChromaDB** —
   files under `data/index/`.
2. The index contains ONLY chunks from `source_list.csv` URLs. Nothing else
   is ever added (this is how "official sources only" is enforced).
3. `build_index.py --rebuild` wipes and rebuilds fully — idempotent.
4. Deliverable: commit/zip `data/index/` so the app starts without re-scraping.

**Done when:** index rebuilds from `source_list.csv` alone; a manual search
returns the exit-load chunk for a "exit load?" style probe.

---

## Step 7 — Retrieval logic

**Goal:** answer-time retrieval + the "no source" path.

**Tasks**
1. `app/retriever.py`:
   - Embed the user question → search top-k (k = 3–5) chunks.
   - If the question names a scheme, pre-filter chunks by `scheme` metadata.
2. **Threshold:** if top score < cutoff → return `NO_SOURCE`.
   Calibrate the cutoff on ~20–30 probe questions from the corpus facts.
3. `NO_SOURCE` never reaches the LLM as an answerable case — it goes straight
   to the refusal template: "I don't have this in my approved sources."
4. No re-ranker, no open-web fallback. Corpus-only, always (PRD FR1).

**Done when:** ≥ 90% of probe queries hit the right chunk; impossible
questions return `NO_SOURCE`.

---

## Step 8 — Retrieval-augmented generation & UI

**Goal:** the tiny UI (Streamlit) with strict grounded answering.

**Tasks**
1. **Layout (PRD FR9–FR12):**
   - Welcome line: *"Hi! I answer factual questions about DoA-approved
     Groww Mutual Fund schemes using official sources only."*
   - 3 clickable example questions (expense ratio? / minimum SIP? / how to
     download capital-gains statement?).
   - Persistent note: **"Facts-only. No investment advice."** + disclaimer
     snippet on the answer screen.
2. **Ask flow:** input → guardrail (input) → retriever → LLM → guardrail
   (output) → render.
3. **System prompt (generator.py):** answer only from supplied chunks; if
   fact absent → `REFUSE`; max **3 sentences**; figures exactly as written in
   the chunk (no arithmetic); exactly one citation URL; end with
   `Last updated from sources: <date>`.
4. **Rendering:** ≤ 3-sentence answer, citation as a real hyperlink, footer
   line, nothing stored between turns (stateless — no chat history).

**Done when:** full flow works end-to-end: welcome → example click →
answer with one official link → advice question gets refused politely.

---

## Step 9 — Edge cases (design decision per case)

| # | Edge case | Handling |
|---|---|---|
| E1 | User pastes PAN/Aadhaar/OTP/email/phone | Input guardrail blocks; **do not store, do not echo**; explain facts-only scope (FR7) |
| E2 | "Should I buy/sell/hold this fund?" | Refusal template + 1 SEBI/AMFI educational link (FR6) |
| E3 | "What are the returns / best fund?" | No computation/comparison; link official factsheet (FR8) |
| E4 | Question about another AMC's fund | Out-of-scope refusal — corpus is Groww MF only |
| E5 | Fact not in corpus (e.g., a fee not on any page) | `NO_SOURCE` refusal — never guess or fill gaps |
| E6 | Ambiguous scheme name ("that ELSS one?") | Ask one clarifying line OR refuse; never mix schemes in one answer |
| E7 | Moral/terrorist/adult abuse of the model | Generic safe refusal, no educational link needed |
| E8 | LLM/network failure mid-answer | Show refusal-style fallback message; never a stack trace |
| E9 | Two chunks disagree (stale vs fresh page) | Prefer the fact with newer `last_updated`; if unclear → `NO_SOURCE` |
| E10 | Very long / empty / gibberish input | Trim/validate input length; empty → prompt to ask a question |

---

## Step 10 — Guardrail test cases (`tests/test_guardrails.py`)

Automated unit tests — the guardrail passes the case in / fails it out:

| # | Test | Input example | Expected verdict |
|---|---|---|---|
| T1 | PAN detector | "My PAN is ABCDE1234F" | `PII_BLOCK`, no echo in reply |
| T2 | Email detector | "contact me at a@b.com" | `PII_BLOCK` |
| T3 | Phone detector | "call me on 9876543210" | `PII_BLOCK` |
| T4 | OTP detector | "the OTP is 445 987" | `PII_BLOCK` |
| T5 | Aadhaar detector | "Aadhaar 1234 5678 9012" | `PII_BLOCK` |
| T6 | PII negative | "What is the expense ratio?" | pass |
| T7 | Advice intent | "Should I buy or sell this ELSS?" | `ADVICE_BLOCK` + educational link |
| T8 | Advice phrasing variants | "which is better / best fund / worth it" | `ADVICE_BLOCK` |
| T9 | Performance intent | "How did it perform this year?" | `PERFORMANCE_BLOCK` + factsheet link |
| T10 | Out-of-scope | "Tell me about HDFC funds" | `OOS_BLOCK` |
| T11 | NO_SOURCE | obscure fact not in any chunk | refusal, no LLM answer |
| T12 | Citation allow-list | forged URL in LLM draft | output blocked; only `source_list.csv` URLs pass |
| T13 | Sentence limit | 4-sentence LLM draft | blocked → regenerate or truncated refusal path |
| T14 | Date stamp | answer missing footer | blocked |
| T15 | Refusal politeness | any refusal output | human-reviewed: polite, ≤ 3 sentences, exactly 1 link |

**Runner:** `python -m tests.test_guardrails` prints a pass/fail matrix.
**Exit bar:** T1–T5 and T12 must be 100%; refusal correctness (PRD G3) ≥ 95%
on `qa_samples.md`; 0 PII anywhere in outputs; 0 returns figures.

---

## Milestones touchpoint

| Week | Steps | Skill |
|---|---|---|
| W1 — Thinking Like a Model | 2, 4 (fact notes), 9 (answer vs refuse lines) | identify exact fact asked |
| W2 — LLMs & Prompting | 8 (prompt + refusal wording), 10 T15 | concise answers, polite refusals |
| W3 — RAG | 4–7 (load → chunk → embed → store → retrieve + citations) | small-corpus RAG |
