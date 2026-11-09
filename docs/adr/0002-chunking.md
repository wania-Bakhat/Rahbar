# ADR 0002: Structure-aware chunks with overlap

- Status: accepted provisionally; measured tuning is pending
- Context: Academic policies rely on clauses and page references. Fixed character splitting can detach a clause from its heading, while very small chunks can split context needed to answer a question.
- Decision: Preserve page and section metadata, prefer heading and paragraph boundaries, fall back to sentence/token boundaries, and use a default 400 whitespace-token target with 50-token overlap. A token is one non-empty Python `str.split()` unit, not a model-specific subword token. Compare 200/25, 400/50 and 600/75 using `eval/tune_chunking.py` and the same golden relevance set before claiming the best configuration.
- Consequences: Overlap can repeat content and increase storage; the 50/400 ratio is 12.5% of target chunk capacity, but actual corpus storage amplification has not been measured. Scanned pages and table ordering require separate review. Do not claim the default is empirically optimal until measurements exist.
- Alternatives considered: Character-only fixed windows disregard clause structure; no overlap reduces repeated storage but risks losing facts at boundaries.
