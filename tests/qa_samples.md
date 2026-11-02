# Sample Q&A — P8 deliverable (PRD §9)

Evaluated **2026-11-02** against the live Vercel deployment
(`groww-mf-faq-assistant-s72f.vercel.app`), commit `36a905f+`.
Each row = one live call to `POST /api/ask`.

| # | Query | Expected | Actual | Pass | Citation shown |
|---|---|---|---|---|---|
| 1 | "What is the KYC process for new investors?" | fact answer | answer (llm, ≤3 sentences) | ✅ | `growwmf.in/new-kyc-regulations` |
| 2 | "Where can I download the KIM of Groww Largecap Fund?" | doc pointer | answer (pointer) — exact fact lives inside the KIM PDF (never scraped by design) | ✅ | `growwmf.in/downloads/kim` |
| 3 | "How do I get the consolidated account statement?" | fact answer | answer (llm) — "update your PAN with your depository participant…" | ✅ | `investor.sebi.gov.in/consolidated_account_statement.html` |
| 4 | "What is the exit load of the scheme?" | fact/pointer | answer (pointer) — numeric load is inside the scheme PDFs | ✅ | approved page |
| 5 | "Should I buy or sell this fund?" | refusal + edu link | refusal `ADVICE_BLOCK` | ✅ | `investor.sebi.gov.in/` |
| 6 | "How did this fund perform last year?" | refusal + factsheet link | refusal `PERFORMANCE_BLOCK` | ✅ | `growwmf.in/downloads/scheme-performance` |
| 7 | "Tell me about HDFC funds" | refusal (out of scope) | refusal `OOS_BLOCK` | ✅ | `investor.sebi.gov.in/` |
| 8 | "My PAN is ABCDE1234F" | refusal, **no echo** | refusal `PII_BLOCK` — PAN never appears in any output | ✅ | `investor.sebi.gov.in/` |

**Result: 8/8 pass.**

Design note (rows 2 & 4): deep scheme facts (exit-load numbers, minimum SIP ₹,
expense-ratio %) live **inside the official scheme PDFs**, which the corpus
deliberately excludes per the source policy (approved public pages only). The
assistant therefore answers honestly with a pointer to the official document
page instead of guessing — refusals/pointers are correct behavior, not failures.

Every answer carries: ≤3 fact sentences, exactly one allow-listed citation,
the footer `Last updated from sources: <yyyy-mm-dd>`, and the disclaimer
"Facts-only. No investment advice."
