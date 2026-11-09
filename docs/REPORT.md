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
pages and 58 Student Handbook pages. The corrected full-corpus Job `indexer-clipped2`
published 1,029 chunks in 839.7 seconds; its output is in
`docs/evidence/20261108-indexer-clipped2.txt`. The API reports the active collection as
ready with 1,029 chunks and the expected embedding-model pin.

## Live evaluation

The corrected 18-question run is in `eval/results.json`. It uses the corrected q12 relevance
section, `6. Generative AI and Assessments`. The evaluator preserves each full answer,
retrieved evidence, citation, per-question timing, and aggregate metric. Manual review found
q08 and q15 returned Rs. 12,000 per credit hour, q09 identified a Careem recruitment drive,
and q11 returned Rule 1 from the superseded prospectus, all with citations matching retrieved
passages. q10 failed twice, including after an API rebuild and fresh cache namespace: it
returned a table-of-contents answer and cited section 1.20 even though clause 1.21 was
retrieved at rank 2. The expected value 1.21 is supported by the corpus and was not changed.
q07 retrieved a footer/table-of-contents chunk rather than Training and Support; a local
source/section filter and regression test have since been added but are not live-verified.
The injection probe safely abstained but missed its annotated relevant chunk.

| Metric | Final value | Status |
| --- | ---: | --- |
| Recall@3 | 0.875 | Corrected-golden full run |
| Recall@5 | 0.875 | Corrected-golden full run |
| Citation validity | 100% (15/15) | Corrected-golden full run |
| Must-abstain correctness | 100% (2/2) | Corrected-golden full run |
| Expected-value accuracy | 85.7% (6/7) | Gate fails on q10 |

The PDF does not set an absolute minimum recall, but it does require the expected-value
checks, at least 95% citation validity, and 100% must-abstain correctness. Citation and
abstention checks pass; the q10 expected-value gate fails. No `eval/baseline.json` is
accepted or created.

## Measured configuration experiments

The real cache-threshold run is in `eval/cache-threshold-results.json`: 0.85 and 0.90 each
had the regular/summer attendance false hit; 0.95 had zero false hits and was the lowest
tested threshold with zero false hits, but it also missed both same-answer paraphrases.
Three chunk configurations remain unmeasured. The Windows run lacked Tesseract; an
OCR-capable temporary container was started, but Docker became unavailable before a result
could be captured. No chunk-tuning measurements are claimed.

## Failure analysis and Kubernetes demonstrations

Record at least four isolated failure-mode runs in `docs/FAILURE-ANALYSIS.md` with their
saved evaluator JSON, observed symptom, diagnostic metric/log, and remedy. The NetworkPolicy
script has already been run against the live cluster, including the UI DNS case; its output
is in `docs/evidence/20261108-network-policy.txt`. The rollout-undo, pod-recovery, and
embedding-pin-mismatch demonstrations still need fresh captured output.

## CI/CD and submission state

CI and CD workflow definitions, dev/prod/CI/CD Kustomize overlays, and Makefile targets are
present. Every test invocation uses `python -m pytest`. Run the local checks and submission
checker after the remaining changes; a local pass does not imply a successful GitHub Actions
run. Git identity is `fahima <fahimasohail@gmail.com>`. `gh auth status` reported that the
existing GitHub token is invalid; under the user's instruction not to try another auth
route, changes will be committed locally but not pushed, and a PR cannot be opened here.

## Student-owned work

See `docs/MANUAL-STEPS.md` for GitHub secrets, `main` branch protection, required authentic
GitHub screenshots, AI disclosure review, the personal engineering reflection, and
Classroom submission. The personal reflection remains explicitly marked
**TO BE WRITTEN BY STUDENT**.
