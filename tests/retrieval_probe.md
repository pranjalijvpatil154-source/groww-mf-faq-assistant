# Step 7 — Retrieval probe set (threshold calibration, IMPLEMENTATION.md Step 7)
# expect = "hit:<keyword in ANY retrieved chunk>" | "NO_SOURCE"
# Note: fact VALUES (exact expense ratio / exit load figures) live inside PDF
# documents that we deliberately did not scrape; for those queries the corpus
# can only surface the official document hub — the refusal decision for missing
# numbers happens downstream (generator REFUSE contract, Step 8).
q|"What is the minimum amount required to invest in mutual funds?"|hit:minimum
# ^ known v1 miss: the direct FAQ chunk ranks #8 (needs re-ranker/re-chunking
#   in a future milestone; top-k is capped at 3-5 by the plan)
q|"How do I download the capital gains statement?"|hit:statement
q|"How is my KYC validated?"|hit:validation
q|"How do I raise a complaint about my folio?"|hit:complaint
q|"What scheme documents are available for Groww schemes?"|hit:.pdf
q|"Where can I download the KIM of Groww Largecap Fund?"|hit:.pdf
q|"Where can I download the factsheet for Groww Largecap Fund?"|hit:.pdf
q|"Where can I download the KIM of an ELSS scheme?"|hit:.pdf
q|"What is a mutual fund?"|hit:mutual fund
q|"How can I reach investor relations officer of Groww Mutual Fund?"|hit:grievance
q|"Information about Mutual Funds Sahi Hai"|hit:sahi
q|"What is a consolidated account statement?"|hit:consolidated
q|"Where can I see KYC guidelines?"|hit:kyc
q|"What is the exact expense ratio of Groww Largecap Fund?"|hit:.pdf
q|"What is the exit load of Groww Liquid Fund?"|hit:.pdf
q|"What is the minimum SIP amount of Groww Liquid Fund?"|hit:.pdf
q|"What is the riskometer level of Groww Value Fund?"|hit:.pdf
q|"What benchmark does the Groww ELSS Tax Saver Fund track?"|hit:.pdf
q|"What is the lock-in period of the ELSS scheme?"|NO_SOURCE
q|"Where can I download the SID for the ELSS scheme?"|NO_SOURCE
q|"How do I check my NAV?"|NO_SOURCE
q|"Tell me about HDFC mutual funds"|NO_SOURCE
q|"What is the price of bitcoin today?"|NO_SOURCE
q|"How did Nifty perform last week?"|NO_SOURCE
