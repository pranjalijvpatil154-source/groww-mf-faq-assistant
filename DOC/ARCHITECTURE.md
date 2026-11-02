# Architecture — Groww Mutual Fund Facts-Only FAQ Assistant

| Field | Value |
|---|---|
| Derived from | `DOC/PRD.md` v1.0 |
| Component | MF Facts-Only FAQ Assistant (RAG, small corpus) |
| Version | 1.0 (Draft) |
| Date | 2026-11-01 |

> **Governing principles (from PRD §3, §7):** facts-only, one official citation
> per answer, ≤ 3 sentences, no advice, no performance claims, no PII, no
> open-web retrieval at answer time.

---

## 1. High-level view

The system is intentionally **small and offline-by-default**: a one-AMC corpus
(15–25 official pages) is ingested once into a local index; at query time,
retrieval is corpus-only and the LLM is constrained to answer from retrieved
chunks with verbatim citations. Two hard guardrails sit in front of and behind
the LLM.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              USER (Browser)                              │
│   Welcome line • 3 example questions • "Facts-only. No investment advice"│
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ question (text only)
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 1 — TINY UI (Streamlit / Gradio, stateless)                       │
│  FR9–FR12: welcome, examples, disclaimer; no fields, no session store    │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 2 — INPUT GUARDRAIL  (deterministic, runs BEFORE the LLM)         │
│  • PII detector (PAN/Aadhaar/account/OTP/email/phone regex) → refuse,    │
│    never store, never echo                     (NFR1, FR7)               │
│  • Advice/opinion intent check → refusal path           (FR6, FR8)       │
│  • Out-of-scope (other AMCs, stocks, macros) → refusal path              │
└───────────────┬──────────────────────────────────────────┬───────────────┘
        allow (factual)                            block (advice/PII/oos)
                ▼                                          ▼
┌───────────────────────────────────────┐   ┌──────────────────────────────┐
│  LAYER 3 — RETRIEVER (corpus-only)    │   │  REFUSAL TEMPLATE ENGINE     │
│  • embed question (same embedder     │   │  • polite facts-only message │
│    as ingestion)                      │   │  • 1 educational link:       │
│  • top-k chunks (local vector index)  │   │    SEBI / AMFI investor-edu  │
│  • score threshold → "no source" if   │   │  • factsheet link for        │
│    nothing relevant                   │   │    performance questions     │
└───────────────┬───────────────────────┘   └──────────────┬───────────────┘
                ▼                                          │
┌──────────────────────────────────────────────────────────┼───────────────┐
│  LAYER 4 — GROUNDED GENERATOR (LLM, strict system prompt)│               │
│  • answers ONLY from retrieved chunks      (FR1)         │               │
│  • ≤ 3 sentences (FR5), plain factual tone (W2)          │               │
│  • citation = URL metadata of the winning chunk (FR3)    │               │
│  • ends with: Last updated from sources: <date>  (FR4)   │               │
│  • EMPTY/low-confidence retrieval → refusal path ────────┘               │
└───────────────┬───────────────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 5 — OUTPUT GUARDRAIL  (verify BEFORE display)                     │
│  • citation URL ∈ approved source list (source_list.csv)   (FR1)         │
│  • sentence-count / date-stamp / disclaimer formatting check (FR4, FR5)  │
│  • against returning computed returns or advice phrasing    (FR8)        │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
                     Answer + citation shown in UI
                (nothing is persisted; memory holds only the turn)
```

---

## 2. Component detail

### 2.1 Ingestion pipeline (offline, run once per corpus update)

| Step | Tool | Notes |
|---|---|---|
| S1. Fetch | `requests` / `httpx` | only approved AMC/SEBI/AMFI URLs |
| S2. Extract text | `trafilatura` / BS4 | strip nav/ads; keep tables for expense ratios |
| S3. Chunk | ~300–500 tokens, slight overlap | keep scheme name + fact type in metadata |
| S4. Embed | `sentence-transformers` (e.g., MiniLM) | one embedder for ingestion AND query |
| S5. Index | FAISS / ChromaDB (local, flat) | metadata: `url`, `page_title`, `scheme`, `fact_hint`, `last_updated` |
| S6. Source ledger | `source_list.csv` | the 15–25 approved URLs — single source of truth for FR1/citation allow-list |

The corpus is a **build artifact** (checked-in index folder), so the app
restarts instantly without re-fetching.

### 2.2 Retrieval (Layer 3)

- Top-k (k=3–5) chunk search; cosine similarity; no re-ranker in v1.
- Threshold tuning is a W3 task: below threshold ⇒ deliberate
  "I don't have this in my sources" refusal (never an unsupported answer).
- Retrieval is **scoped**: index contains only the approved corpus — the
  architecture itself enforces PRD FR1 (no open-web retrieval at answer time).

### 2.3 Generator (Layer 4)

- **Model:** pluggable. Default: any chat LLM behind a rubric-quality API
  (e.g., Gemini/GPT-class) since the prompt rubric (W1/W2) matters more than
  model size; a local small model (e.g., Llama-3 8B class) is an acceptable
  fallback for zero-egress setups.
- **System prompt contract (W2 focus):**
  1. Answer only from the given chunks; if not present, output `REFUSE`.
  2. Max 3 sentences; no recommendations, comparisons, or return figures.
  3. Cite exactly one chunk's URL in the mandated footer line.
  4. Never invent, never complete missing figures with guesses.
- Query rewrite: none in v1 (W1 decision: identify the exact fact asked —
  handled by prompt, not a separate model).

### 2.4 Guardrails (Layers 2 & 5)

- Deterministic regex/keyword layers are used wherever a rule can decide
  (PII, date-stamp presence, citation allow-list, sentence count).
- LLM-assisted judgement is used **only** for the advice/opinion intent check,
  with the deterministic refusal templates as the output path.
- Failure mode: any guardrail failure ⇒ refusal message, never a raw LLM
  output.

### 2.5 UI (Layer 1)

- Single page; three elements per PRD FR9–FR12; questions submitted as plain
  text; answers rendered with the citation as a real hyperlink.
- **Stateless by design:** no session store, no chat history persisted, no
  account system — directly implementing NFR1 and reducing the PII surface.

---

## 3. Data model

```
source_list.csv      → { source_id, url, publisher[AMC|SEBI|AMFI], doc_type,
                         scheme, last_updated, notes }
vector_index/        → { chunk_id, vector, url, page_title, scheme,
                         fact_hint, last_updated }
qa_samples.md/csv    → { query, expected_fact, expected_refusal?, url, pass }
```

Nothing else is stored. There is no user store and no conversation log.

---

## 4. Repository layout (proposed)

```
newfolder/
├── DOC/
│   ├── ProblemStatment.txt        # problem statement (done)
│   ├── PRD.md                     # product requirements (done)
│   └── ARCHITECTURE.md            # this document
├── ingest/
│   ├── fetch_pages.py             # S1–S2
│   ├── build_index.py             # S3–S5
│   └── source_list.csv            # S6
├── app/
│   ├── ui.py                      # Layer 1
│   ├── guardrails.py              # Layers 2 & 5
│   ├── retriever.py               # Layer 3
│   ├── generator.py               # Layer 4 + prompt template
│   └── refusals.py                # refusal templates + educational links
├── data/
│   └── index/                     # built vector index (artifact)
├── tests/
│   └── qa_samples.md              # 5–10 sample Q&A deliverable
└── README.md                      # setup, scope, known limits
```

---

## 5. Two runtime flows

### Flow A — factual question ("What is the exit load of <scheme>?")

1. L2 PII filter passes; intent check classify `factual`.
2. L3 retrieves exit-load chunk from the scheme's fee page.
3. L4 composes ≤ 3 sentences strictly from the chunk; attaches
   `url` (fee page) and date stamp.
4. L5 verifies: citation ∈ `source_list.csv`, ≤ 3 sentences, date present.
5. UI shows answer + citation. Nothing stored.

### Flow B — advice question ("Should I buy or sell this fund?")

1. L2 intent check classifies `advice` (or L5 catches it if L2 passes it).
2. Refusal template engine picks template + one SEBI/AMFI educational link.
3. No LLM generation needed on this path (LLM used only in gray cases).
4. Performance-questions variant: refusal + link to the official factsheet.

---

## 6. Technology choices (v1) with rationale

| Concern | Choice | Why |
|---|---|---|
| UI | Streamlit (or Gradio) | fastest tiny-UI route per PRD FR9–FR12 |
| Language | Python 3.10+ | team stack for W1–W3 |
| Extraction | trafilatura | clean text from AMC pages incl. HTML tables |
| Embeddings | sentence-transformers MiniLM | local, small-corpus adequate, consistent query/index embedder |
| Vector store | FAISS (flat) / ChromaDB | local, zero-infra, correct size for ≤ ~100 chunks |
| LLM | pluggable chat LLM via API key from env | rubric-quality prompting (W2) is the differentiator; `OPENAI_API_KEY`/`GEMINI_API_KEY` style env only, never in code |
| Session | none | NFR1: no PII, no persistence |

---

## 7. Requirements → architecture traceability

| PRD ref | Enforced by |
|---|---|
| FR1 corpus-only retrieval | §2.1 S6 (source ledger) + scoped index (§2.2) + citation allow-list check (§2.4) |
| FR2 fact categories | corpus coverage validation in Milestone 1 (PRD §5.1) |
| FR3 one citation | chunk metadata URL (§2.1 S5) + L5 check (§2.4) |
| FR4 date stamp | metadata `last_updated` + L5 format check |
| FR5 ≤ 3 sentences | system prompt + L5 count check |
| FR6 polite refusal + educational link | L2 intent check → L refusal engine (§2.4) |
| FR7 no PII | L2 regex detector + stateless UI (§2.5) |
| FR8 no performance claims | L2 intent detection (returns → refusal+factsheet link) + L5 phrasing check |
| FR9–FR12 tiny UI | §2.5 |
| NFR1 privacy | no store, no echo, no logs (§3, §6) |
| NFR4 latency | local index + short generation; no re-ranker in v1 |

---

## 8. Evaluation & test hooks

- `tests/qa_samples.md` doubles as the deliverable and the regression suite:
  each row asserts {expected fact | expected refusal, expected URL, ≤3
  sentences, date stamp present}.
- Automated checks: refusal correctness, citation validity, format rules.
- Human checks (W1/W2 rubric): politeness of refusal, citation wording,
  answer identifiability ("the exact fact asked").

---

## 9. Known limitations (carried into README)

- Facts are as fresh as the last ingest; ingestion is manual in v1.
- Gray-area intents (e.g., "is direct better for tax?") rely on prompt
  quality; deterministic refusal on ambiguity is preferred to a risky answer.
- No multilingual support assumed; corpus languages only.
- Sub-3-sentence constraint can omit qualifying nuance — the citation link is
  the user's path to the full official detail.

---

## 10. Open items for the next milestone

1. Freeze the final Groww MF scheme set (validate official pages) → then
   fetch + build index (ingestion S1–S6).
2. Decide LLM provider available to the team (API vs. local).
3. Tune retrieval threshold on the sample Q&A set.
4. Finalize disclaimer wording (PRD Appendix A) and drop it into the UI.
