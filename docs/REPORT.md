# RAHBAR assignment report

**Status:** Working report; update every pending row only after the named live run finishes.
The assignment PDF is the grading source of truth.

## System and corpus

RAHBAR separates an on-demand indexer Job (the Chroma writer) from a three-replica FastAPI
reader, an nginx chat UI, persistent Chroma and Redis, and an Ingress. The API and indexer
share the `nomic-embed-text` pin; Ollama generation uses `llama3.2:3b` on the host. The
namespace is `rahbar`, and the current Minikube host route is `192.168.127.254`.

The corpus contains eight public FAST-NUCES PDFs covering 280 pages. It includes current
and superseded policy versions, OCR-only pages, tables, long definitions, exact terms, and
deliberately absent topics. Source URLs and checksums are recorded in `corpus/MANIFEST.md`;
raw PDFs are excluded from Git.

The fee-information PDF uses a page-specific left/right extraction split to keep the
Rs. 12,000 tuition-per-credit-hour statement separate from the right-column miscellaneous
fee table. A regression test checks the extracted order. General PDF extraction clips text
to the visible page bounds: the audit found out-of-page text on 29 Academic Rules Handbook
pages and 58 Student Handbook pages. The final corrected full-corpus Job published 1,029
chunks in 857.5 seconds; its output is in `docs/evidence/20261110-indexer-final.txt`. The
earlier 839.7-second run remains in `docs/evidence/20261108-indexer-clipped2.txt`. The API
reports the active collection as ready with 1,029 chunks and the expected embedding-model
pin.

## Live evaluation

The latest completed 18-question run is in `eval/results.json`; its metrics are also in
`eval/baseline.json`, but that baseline is provisional pending a live answer fix and rerun.
It uses the corrected q12 relevance section, `6. Generative AI and
Assessments`. The evaluator preserves each full answer, retrieved evidence, citation,
per-question timing, and aggregate metric. q07 now retrieves “10. Training and Support” on
page 60. q08 and q15 return Rs. 12,000 per credit hour; q11 returns Rule 1 from the
superseded prospectus. The initial q10 defect occurred when citation validation fell back
to a nearby table-of-contents passage. A source-and-section filter for that clause-number
question now yields 1.21 from current rule 1.21, both in a focused live check and the final
full run. The injection probe safely abstained but still missed its annotated relevant chunk.
Manual review also found q09 falsely abstained: the API retrieved the exact
`3. Recruitment Drives` passage on page 79 (similarity 0.711), whose text names multiple
2023-24 drives, but returned the no-evidence response. A narrow verbatim-evidence recovery
and regression tests are in the working tree. The live request did not reach that code path:
the API returned an Ollama embedding timeout, and Minikube inspection failed while C: had
zero free bytes. The previous run and baseline remain the latest complete measurements,
but are not accepted as final until q09 and the full set are rerun.

| Metric | Final value | Status |
| --- | ---: | --- |
| Recall@3 | 0.9375 | Latest complete run before q09 repair |
| Recall@5 | 0.9375 | Latest complete run before q09 repair |
| Citation validity | 100% (14/14) | Of citations emitted; q09 had no citation because it falsely abstained |
| Must-abstain correctness | 100% (2/2) | Latest complete run; q16 and q17 |
| Expected-value accuracy | 100% (7/7) | Latest complete run before q09 repair |

The previous run met the numeric gates: expected-value checks, at least 95% citation
validity, and 100% must-abstain correctness. Qualitative review found one false abstention
among the 15 answerable non-injection questions (q09), so the baseline is provisional rather
than final. q18 safely abstained but injection retrieval recall was 0.00; that remains a
known retrieval limitation.

## Measured configuration experiments

The real cache-threshold run is in `eval/cache-threshold-results.json`: 0.85 and 0.90 each
had the regular/summer attendance false hit; 0.95 had zero false hits and was the lowest
tested threshold with zero false hits, but it also missed both same-answer paraphrases.
The full-corpus three-configuration run measured recall@3/5 of 0.875 for 200:25, 400:50,
and 600:75, with 1,172, 1,029, and 998 chunks respectively. No configuration improved
retrieval in this run. We retained 400:50 as the middle-size setting. The Job printed all
metrics but failed at its final JSON path serialization (`/corpus` was outside `/workspace`);
the captured stdout is in `docs/evidence/chunk-tuning-job-stdout.txt`, and the results artifact
marks that provenance. A regression test now covers external mounted paths.

## Failure analysis and Kubernetes demonstrations

Four isolated API failure modes were run on the same five-question subset, with successful
rollout and restoration to `off` after each. All four preserved recall@5 0.75, citations
3/3, abstention 1/1 and expected values 2/2; this small sample did not expose a regression.
The raw per-question results and observed interpretation are in `docs/FAILURE-ANALYSIS.md`
and `docs/evidence/20261111-failure-mode-runs.txt`. The NetworkPolicy script passed all checks, including UI DNS;
output is in `docs/evidence/20261110-network-policy.txt`. Rollout undo, pod recovery, and
embedding-pin mismatch demonstrations are captured in the dated 20261110 evidence files.
These failure-mode runs predate the q09 recovery change; their five-question subset does
not include q09.

## CI/CD and submission state

CI and CD workflow definitions, dev/prod/CI/CD Kustomize overlays, and Makefile targets are
present. Every test invocation uses `python -m pytest`. Targeted tests and Kustomize builds
pass; the latest submission checker reported 166 passes, 4 warnings, and 0 failures. Git
identity is `fahima <fahimasohail@gmail.com>`. GitHub authentication failed earlier, so no
credential workaround was attempted; only `dev` may be pushed.

## Student-owned work

See `docs/MANUAL-STEPS.md` for GitHub secrets, `main` branch protection, required authentic
GitHub screenshots, AI disclosure review, the personal engineering reflection, and
Classroom submission. The personal reflection remains explicitly marked
**TO BE WRITTEN BY STUDENT**.
