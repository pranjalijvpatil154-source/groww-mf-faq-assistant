# API retrieval-threshold calibration (gemini-embedding-001 space)

Date: 2026-11-02 · Script: `tests/api_calibration.py` · 13 probes

| Field | Value |
|---|---|
| Document vectors | 31 chunks × 3072-d, `RETRIEVAL_DOCUMENT` (data/index/gemini_vectors.json) |
| Query embedding | same model, `RETRIEVAL_QUERY` |
| In-corpus min score | **0.6906** (riskometer question) |
| Out-of-corpus max score | **0.6886** (NAV-yesterday question) |
| Chosen threshold | **0.65** (set in `api/ask.py`) |

## Full sweep

```
[in ] 0.7549  (GROWW-KYC-001#c02)  How is my KYC validated?
[in ] 0.7776  (GROWW-KIM-001#c00)  Where can I download the KIM of Groww Largecap Fund?
[in ] 0.8132  (GROWW-GRV-001#c00)  Who do I contact for grievances on a Groww fund?
[in ] 0.7625  (SEBI-STMT-001#c00)  What is the consolidated account statement ...?
[in ] 0.7218  (GROWW-SID-001#c00)  Where do I find the scheme information document?
[in ] 0.6906  (GROWW-RSK-001#c00)  What risk level does the riskometer show?
[in ] 0.7719  (GROWW-KYC-001#c01)  How do new KYC regulations affect existing investors?
[in ] 0.7063  (AMFI-SHI-001#c04)  How do mutual funds work for beginners?
[out] 0.6886  (GROWW-KIM-001#c00)  What was the NAV yesterday of Groww Largecap Fund?
[out] 0.6804  (AMFI-SHI-001#c05)  Recommend me the best fund for my retirement goals
[out] 0.5240  (GROWW-KIM-001#c00)  Tell me a joke about cats
[out] 0.6303  (AMFI-EDU-001#c00)  Who is the ABC of XYZ company?
[out] 0.5902  (SEBI-STMT-001#c00)  How do I open a savings bank account?
[out] 0.5726  (AMFI-EDU-001#c00)  What is the weather in Mumbai today?
```

## Rationale

- 0.65 keeps all 8 genuine questions (score ≥ 0.6906) retrievable.
- Pure nonsense ("weather", "joke", "savings account") hits the `NO_SOURCE` refusal
  instead of wasting a generation call.
- "Advice"/"NAV"-style borderline probes still pass retrieval but hit the
  ground-truth layer: the LLM's contract refuses anything not in the chunk text,
  which degrades to the honest pointer answer — correct by design.
- "Recommend the best fund" is additionally blocked earlier by the input
  guardrail (`ADVICE_BLOCK`), so its probe score is irrelevant.
