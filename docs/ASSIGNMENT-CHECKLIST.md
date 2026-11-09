# Assignment 02 requirement checklist

Source of truth: `D:\SCD\Assignment 02, RAHBAR Grounded RAG on Kubernetes.pdf` (20 pages).
This checklist records current evidence; a file existing is not treated as proof of a
runtime requirement. Update statuses only after the corresponding check or demonstration.

Status key: **PASS** verified; **IN PROGRESS** work underway; **PENDING** not yet verified;
**STUDENT ACTION** needs a team member or account owner; **KNOWN FAILURE** real failure
recorded without hiding it.

## Product outcome and corpus

- **PASS** Grounded question-answering service is deployed to the `rahbar` namespace.
- **PASS** Responses include structured citations copied from retrieved source, section,
  and page; current live attendance check cited clause 1.21.
- **PASS** Out-of-scope questions abstain; first full live evaluation had 2/2 correct.
- **PASS** Corpus has eight public FAST-NUCES PDFs, 280 pages, current/superseded policy
  versions, scanned documents, a table, long definitions, deliberately absent topics,
  and exact-term content. `corpus/fetch.py --verify` previously reported 8/8 checksums.
- **PASS** Raw PDFs are local/ignored; source URLs and SHA-256 hashes are recorded in the
  manifest.
- **PASS** OCR path covers scanned pages; full index job logged chunks for all eight PDFs.
  OCR character-level review remains a team quality review, not claimed as completed.
- **PASS** The fee prospectus is extracted by left/right page columns, preserving tuition
  paragraphs separately from the miscellaneous-fee table. A regression test covers that
  ordering. The corrected visible-page index completed with 1,029 chunks; the tuition
  section carries Rs. 12,000 per credit hour. The 2026 fee PDF was visually checked.

## Pipeline and query behavior (PDF sections 3.1-3.4)

- **PASS** Extract, clean, structure-aware chunk, embed, and Chroma store stages exist.
- **PASS** Chunk metadata contains source, section, page, doc_version, and superseded.
- **PASS** Indexer is the sole Chroma writer; it publishes a completed generation.
- **PASS** API uses the same pinned `nomic-embed-text` model; live readiness matched it
  and embedding dimension was verified as 768.
- **PASS** Semantic cache uses Redis, skips follow-ups/abstentions/invalid answers, and
  switches key namespace when the published index generation changes. ADR explains why
  API-side invalidation follows Redis API-only ingress.
- **PENDING** Measure at least three chunk size/overlap configurations on the same real
  corpus and golden relevance pairs; record recall@5, chunk count, and shipped choice.
- **PASS** Measured thresholds 0.85, 0.90 and 0.95 on six labeled pairs. Both 0.85 and
  0.90 falsely matched regular and summer attendance; 0.95 had zero false hits and is the
  lowest tested threshold meeting the rule, but caught 0/2 same-answer paraphrases. Results
  are in `eval/cache-threshold-results.json`.
- **PASS** Model output is schema-validated, citation-checked, retried/fallback handled;
  injection-safe behavior is included in tests and golden set.

## Kubernetes (PDF sections 4.1-4.8)

- **PASS** Required namespace, 3-replica API Deployment, UI Deployment, persistent Chroma
  StatefulSet, persistent Redis Deployment, indexer Job and weekly CronJob, four ClusterIP
  Services, one-host Ingress, ConfigMap, placeholder Secret, NetworkPolicies, and API HPA
  are defined.
- **PASS** API has startup/liveness/readiness probes, requests/limits, zero-unavailable
  rolling update, and graceful termination. Probe timeouts were increased after observed
  delays and Chroma restart during evaluation.
- **PASS** Default-deny network policy plus scoped allowances are implemented. Both Ollama
  egress rules and the ConfigMap URL use the active Minikube host route `192.168.127.254`;
  `scripts/set_ollama_network_ip.sh` updates all three together and was verified here.
- **PASS** Captured real resource samples for full-corpus index run: 25 samples, max
  observed 553 MiB memory and 966 millicores CPU. This is sampled, not an absolute peak.
- **PASS** Captured API HPA at 3%/70%, 3 replicas, and three API endpoints in evidence.
- **PASS** Re-ran every NetworkPolicy allow/deny check against the live policies, including
  UI DNS and both Ollama paths; all expected outcomes passed. Output is saved in
  `docs/evidence/20261108-network-policy.txt`.
- **PENDING** Demonstrate API image rollout and rollback with `kubectl set image`,
  `rollout status`, `rollout undo`, and a successful post-undo readiness/smoke check.
- **PENDING** Delete one serving API pod and verify a replacement becomes ready and the
  endpoint count returns to three.
- **PENDING** Demonstrate embedding-pin mismatch: change only API EMBED_MODEL, show
  `/readyz` 503 and a log naming expected/actual, restore the pin, and verify readiness.
- **PASS** Readiness and liveness behavior, model-pin guard, JSON logs, request IDs,
  request/retrieval/generation/cache/abstention/fallback/token metrics are implemented.

## Evaluation (PDF section 5)

- **PASS** Golden set has 18 questions: 10 ordinary, 2 version-sensitive, 3 exact-term,
  2 must-abstain, and 1 injection. Relevant source/section pairs are listed.
- **KNOWN FAILURE** Corrected-golden full run on the 1,029-chunk index scored
  recall@3=0.875 and recall@5=0.875; citation validity 100% (15/15); abstention
  correctness 100% (2/2); expected-value accuracy 6/7. By type, recall@5 was ordinary 0.90,
  version-sensitive 1.00, exact-term 1.00 and injection 0.00. q08, q11 and q15 passed.
  q10 failed despite retrieving clause 1.21 at rank 2; q07 and the injection question missed
  their annotated passages. See `eval/results.json` for all answers and evidence.
- **PASS** `eval/run_eval.py` retains per-question responses/retrieval evidence in the
  results artifact and has checkpoint recovery. Unit tests pass with `python -m pytest`.
- **PASS** Focused live q08/q11/q15 checks returned Rs. 12,000 per credit hour, Rule 1 in
  the superseded prospectus, and Rs. 12,000 per credit hour, respectively, with retrieved
  source citations. Evidence is in `docs/evidence/focused-q08-q11-q15.json`.
- **KNOWN FAILURE** q10 still cited 1.20 after an API image rebuild and a fresh cache
  namespace. The evidence-based unit test passes, but the live runtime response remains
  wrong; do not count q10 as fixed. The q12 relevance label was corrected to
  `6. Generative AI and Assessments` based on the handbook passage retrieved in the first run.
- **IN PROGRESS** q07's source PDF contains section `10. Training and Support`; local
  extraction produces that exact section metadata. A source-plus-section retriever filter
  and regression test were added and pass locally, but have not been deployed or verified
  against live Chroma.
- **PENDING** Create `eval/baseline.json` only after reviewing and accepting the healthy
  run; no gate-passing baseline is currently accepted.
- **PENDING** Run at least four of the six PDF failure modes one at a time. Save raw
  metrics/logs and record observed symptom, diagnosis, stage, remedy, and rerun.
- **PENDING** Review evaluator results for unsupported claims, actual question scope,
  evidence use, citation relevance, and abstention; record known limitations honestly.

## CI/CD, engineering notes, and submission (PDF sections 6-10)

- **PASS** CI/CD workflow definitions cover lint/type checks, coverage tests, strict
  manifests, image builds and scan, fixture e2e evaluation, SHA-tagged publishing, and
  ephemeral deployment smoke test. Every publishing/deploy job is gated with `needs:`;
  workflow permissions are least-privilege and actions version-pinned.
- **PASS** Makefile, CI and CD test invocations use `python -m pytest`.
- **IN PROGRESS** Ruff, API mypy (25 files), indexer mypy (10 files), Kustomize builds
  for dev/prod/ci/cd, API targeted tests (27 passed), and indexer/eval tests (15 passed)
  passed. Submission checker reported 165 passed, 3 warnings and one failure: no baseline.
  Do not create a baseline while q10 fails its expected-value gate. Docker/Minikube is
  currently unreachable, so live checks and the full API test suite remain unverified.
- **PASS** Four ADRs and architecture, corpus, pipeline, failure, engineering, and AI-use
  documentation exist; update measured values after actual runs.
- **STUDENT ACTION** Both partners review AI disclosure and add any other AI tools used.
- **STUDENT ACTION** Write the personal >1-hour failure reflection from real team notes;
  do not use invented content. Placeholder is in `docs/ENGINEERING-NOTES.md`.
- **STUDENT ACTION** Configure Docker Hub Actions secrets; configure `main` branch
  protection with PR, one approval, and required CI; capture real protected-branch,
  blocked-merge, and green-merge screenshots.
- **PENDING** Submission checker passes with all non-personal requirements addressed.
- **STUDENT ACTION** Push only `dev`, open dev-to-main PR, obtain required review/checks,
  and submit repository, successful CD run, Docker Hub SHA image links, and committed
  results/baseline on Google Classroom.

## Current blocking sequence

1. Restore Docker Desktop/Minikube access (instructions in `docs/MANUAL-STEPS.md`); the
   cluster API times out and the temporary chunk-tuning run produced no saved result.
2. Run the three chunk configurations and at least four isolated failure modes; deploy and
   live-verify the new q07 section filter where appropriate.
3. Capture rollout undo, pod recovery, and embedding-pin mismatch demonstrations.
4. Refresh evidence, run the checker after live work, and commit locally on `dev`. The
   baseline remains unaccepted because q10 fails. GitHub authentication is invalid; no push
   or PR was attempted after that failure.
