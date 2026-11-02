# PRD — Groww Mutual Fund Facts-Only FAQ Assistant

| Field | Value |
|---|---|
| Product | Groww (chosen from shortlist: INDMoney, Groww, PowerUp Money, Wealth Monitor, Kuvera) |
| Feature | Facts-Only FAQ Assistant for mutual fund scheme questions (RAG-based) |
| Version | 1.0 (Draft) |
| Date | 2026-11-01 |
| Status | For review |
| Source brief | `DOC/ProblemStatment.txt` |

---

## 1. Summary

Build a small, facts-only FAQ assistant for mutual fund scheme questions in the
Groww context. It answers objective questions — expense ratio, exit load,
minimum SIP, ELSS lock-in, riskometer, benchmark, statement downloads — using
**only official public pages** (Groww AMC / SEBI / AMFI), and shows **one clear
citation link** in every answer. Opinionated and portfolio questions are politely
refused. No advice, no performance claims, no PII.

**Product choice rationale:** Groww was selected because it operates its own
AMC (Groww Mutual Fund), allowing the retrieval corpus to be scoped cleanly to
one AMC and 3–5 schemes, as the brief requires.

---

## 2. Problem

- Scheme facts (fees, loads, minimums, risk levels, benchmarks, document
  downloads) are scattered across factsheets, KIM/SID docs, scheme FAQs, and
  SEBI/AMFI pages.
- Retail users comparing schemes cannot quickly verify a single fact with a
  trustworthy source.
- Support/content teams at Groww repeatedly answer the same factual questions
  by hand.
- Where answers exist elsewhere, they often come from blogs/aggregators that
  are outdated or wrong, creating compliance and trust risk.

---

## 3. Goals

| # | Goal | Measure |
|---|---|---|
| G1 | Every answer carries exactly one authoritative citation | 100% of answers in sample Q&A include an official link |
| G2 | Answers are short and factual | ≤ 3 sentences per answer |
| G3 | Unsafe questions are refused safely | ≥ 95% refusal correctness on opinion/advice/PII/advice-adjacent queries in the test set |
| G4 | Zero PII acceptance or storage | No field or log captures PAN/Aadhaar/OTP/email/phone |
| G5 | Zero performance claims | No returns computed, compared, or implied; redirect to official factsheet |
| G6 | Working prototype deliverable | App/notebook link or ≤ 3-min demo video |

**Non-goals**
- No buy/sell/hold recommendations or portfolio suggestions.
- No return calculation/comparison, ranking, or "best fund" answers.
- No user accounts, no data collection, no conversation history storage.
- No full Groww-app integration in this milestone — standalone tiny UI.
- No new content authoring beyond what official pages state.

---

## 4. Target users

1. **Retail user comparing schemes** — wants "what is the exit load of scheme X?"
   answered in one line with a source to trust.
2. **Support/content team member** — wants a consistent, cited answer to reuse
   for repetitive MF questions.

Personas are deliberately narrow; the assistant is not a research tool or an
advisor.

---

## 5. Scope

### 5.1 AMC and schemes

- **AMC:** Groww Mutual Fund (Groww Asset Management Company).
- **Schemes (3–5), one per category:**
  1. Large-cap (active)
  2. Flexi-cap (active)
  3. ELSS / tax-saver (3-year lock-in)
  4. Optional: one index fund / ETF as a passive comparison point

> **Note:** Final scheme names must be validated in Milestone 1 against the
> official Groww Mutual Fund scheme pages. If a planned category (e.g., ELSS)
> has no live official scheme page with KIM/SID + factsheet, swap it for an
> available category. The corpus is built **only** from pages that exist.

### 5.2 Corpus (15–25 official public pages)

| Source type | Examples | Owner |
|---|---|---|
| AMC scheme pages | Factsheets, KIM, SID, scheme FAQs, fee/charges pages | Groww AMC |
| AMC service pages | Statement / capital-gains statement download guides, query escalation | Groww AMC |
| Regulator | SEBI mutual fund pages, categorization/performance- disclosure rules | SEBI |
| Industry body | AMFI NAV/factsheet standards, investor education pages | AMFI |

Excluded: third-party blogs, aggregator sites, news articles, screenshots of
private back-ends, paywalled or login-gated pages.

---

## 6. Functional requirements

### 6.1 Answer flow (RAG, small corpus)

- **FR1.** Retrieve from the approved corpus only (15–25 URLs, scraped/cleaned
  locally). No open-web retrieval at answer time.
- **FR2.** Answer factual queries about: expense ratio, exit load, minimum SIP,
  lock-in (ELSS), riskometer level, benchmark, document/statement downloads,
  other scheme facts present in the corpus.
- **FR3.** Every answer shows **one** citation link, clearly labeled, pointing
  to the exact official page the fact came from.
- **FR4.** Every answer ends with `Last updated from sources: <date>`.
- **FR5.** Answers are at most 3 sentences.

### 6.2 Refusal flow

- **FR6.** Politely refuse opinionated/portfolio/advice questions
  ("Should I buy/sell/hold?", "Which is better?", "Is this right for me?") with
  a facts-only message and **one relevant educational link** (e.g., SEBI or
  AMFI investor-education page).
- **FR7.** Refuse and do not store any PII (PAN, Aadhaar, account numbers,
  OTPs, emails, phone numbers); if provided, do not echo it back.
- **FR8.** For performance/returns questions, refuse to compute or compare;
  link the official factsheet page instead.

### 6.3 Tiny UI

- **FR9.** Welcome line.
- **FR10.** Three clickable example questions, e.g.:
  1. "What is the expense ratio of <scheme>?"
  2. "What is the minimum SIP for <scheme>?"
  3. "How do I download the capital-gains statement?"
- **FR11.** Persistent note: **"Facts-only. No investment advice."**
- **FR12.** Disclaimer snippet visible on every screen where answers appear.

### 6.4 Sample flows

| User asks | Assistant does |
|---|---|
| "Expense ratio of <large-cap scheme>?" | 1-sentence fact + AMC fee page link + date stamp |
| "ELSS lock-in period?" | Fact (3 years) + SID/AMFI page link + date stamp |
| "Should I buy or sell this fund?" | Polite refusal + SEBI/AMFI investor-education link |
| "How has this fund performed / returns?" | Refusal to compare; link to official factsheet |
| "My PAN is ABCDE1234F" | Refuse, do not store, do not repeat; explain facts-only scope |
| "Direct plan vs regular plan — which is better?" | Refusal + educational link; offer objective definition if present in corpus |

---

## 7. Non-functional requirements

- **NFR1. Privacy:** no PII input fields, no PII logging, no persistence of
  conversations.
- **NFR2. Compliance posture:** facts-only; disclaimer always visible;
  citations mandatory; no third-party-blog sources.
- **NFR3. Transparency:** date-stamped answers; corpus source list published
  as deliverable (CSV/MD).
- **NFR4. Latency (soft):** answer within ~5 s for prototype.
- **NFR5. Portability:** runs as a small app or notebook; demo video fallback.

---

## 8. Milestones mapping

| Milestone | Focus | PRD section served |
|---|---|---|
| W1 — Thinking Like a Model | Identify exact fact asked; answer vs. refuse decision | §6.1, §6.2, §8 sample flows |
| W2 — LLMs & Prompting | Instruction style, concise phrasing, polite refusals, citation wording | §6.1 FR5, §6.2 FR6–FR8, §6.3 |
| W3 — RAG (only) | Small-corpus retrieval with accurate citations from AMC/SEBI/AMFI pages | §6.1 FR1–FR3, §5.2 |

All milestones use the **same product (Groww)** and the same declared scope.

---

## 9. Deliverables & acceptance criteria

| Deliverable | Acceptance criteria |
|---|---|
| Working prototype (link or ≤3-min video) | Runs; answers FQ types of §6.1; refusals per §6.2 |
| Source list (CSV/MD) | 15–25 URLs; all AMC/SEBI/AMFI; no blogs |
| README | Setup steps; scope (AMC + schemes); known limits |
| Sample Q&A file | 5–10 queries with answers + links + date stamps |
| Disclaimer snippet | Exact text used in UI, with the "Facts-only. No investment advice." note |

---

## 10. Risks & known limits

| Risk | Mitigation |
|---|---|
| Scheme pages change (fact becomes stale) | Date-stamp every answer; keep source list versioned |
| Chosen categories (e.g., ELSS) lack live official pages | Milestone-1 validation step; swap schemes, keep categories coverage goal |
| Users seed the chat with advice-seeking phrasing | Strong refusal instruction + educational link (FR6) |
| PII leakage into logs | No input persistence; log-free prototype; README documents this |
| Model hallucinated facts / wrong citation | Corpus-grounded retrieval only; citation must match retrieved page; sample Q&A review |

**Known limits to state in README:** small corpus (one AMC, 3–5 schemes),
facts may lag the latest factsheet, no coverage of other AMCs, no advice
capability by design.

---

## 11. Open questions

1. Exact final scheme set for the corpus (validate official Groww MF pages).
2. Prototype stack (Streamlit/notebook + small local index vs. hosted app).
3. Embedding/index strategy for the W3 RAG build (this PRD leaves it open;
   W3 workstream decides).
4. Whether optional index-fund/ETF scheme is included in v1 scope.

---

## Appendix A — Disclaimer snippet (draft, to be finalized in W2)

> This assistant answers factual questions about mutual fund scheme details
> using official public sources (AMC, SEBI, AMFI) only. It shows one source
> link for every answer. It does **not** give investment advice, does **not**
> comment on which fund to buy or sell, and does **not** compare or predict
> returns. Facts-only. No investment advice. Please read the official scheme
> documents before acting.

---

## Appendix B — Abbreviations

| Abbr | Full form |
|---|---|
| AMC | Asset Management Company |
| MF | Mutual Fund |
| ELSS | Equity Linked Savings Scheme (3-year lock-in, Sec. 80C) |
| SIP | Systematic Investment Plan |
| SEBI | Securities and Exchange Board of India |
| AMFI | Association of Mutual Funds in India |
| KIM | Key Information Memorandum |
| SID | Scheme Information Document |
| RAG | Retrieval-Augmented Generation |
| PII | Personally Identifiable Information |
| PRD | Product Requirements Document |
