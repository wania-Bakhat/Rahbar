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
- **PASS with a recorded tooling error** The full-corpus run completed all three retrieval
  measurements: 200:25 = 0.875 recall@3/@5 (1,172 chunks), 400:50 = 0.875/0.875
  (1,029 chunks), and 600:75 = 0.875/0.875 (998 chunks). The Job then failed only while
  serializing its JSON because `/corpus` was outside `/workspace`; the table is preserved
  from actual Job stdout, with the failure and provenance recorded in the result artifact.
  A regression test covers the corrected external-path serialization. No config improved
  retrieval; 400:50 remains the middle-size setting.
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
  UI DNS and both Ollama paths; all expected outcomes passed. Output:
  `docs/evidence/20261110-network-policy.txt`.
- **PASS** Rolled to a known previous API image, used `kubectl rollout undo`, and verified
  three ready replicas plus `/readyz`. Evidence: `docs/evidence/20261110-rollout-undo.txt`.
- **PASS** Deleted one serving API pod; the controller replaced it and the Service returned
  to three endpoints. Evidence: `docs/evidence/20261110-pod-recovery.txt`.
- **PASS** Changed only the API embedding pin, observed `/readyz` 503 with expected/actual
  values, restored the pin, and verified readiness. Evidence:
  `docs/evidence/20261110-embedding-pin-mismatch.txt`.
- **PASS** Readiness and liveness behavior, model-pin guard, JSON logs, request IDs,
  request/retrieval/generation/cache/abstention/fallback/token metrics are implemented.

## Evaluation (PDF section 5)

- **PASS** Golden set has 18 questions: 10 ordinary, 2 version-sensitive, 3 exact-term,
  2 must-abstain, and 1 injection. Relevant source/section pairs are listed.
- **PROVISIONAL BASELINE with known quality failures** The latest complete run on the
  1,029-chunk index scored recall@3/@5=0.9375; citations 14/14; must-abstain correctness
  2/2; expected values 7/7. q07, q08, q10, q11, and q15 passed. q18 safely abstained but
  retrieval recall was 0.00. q09 falsely abstained despite retrieving the exact recruitment
  section on page 79. This run is retained as evidence but its baseline is not final.
- **PASS** `eval/run_eval.py` retains per-question responses/retrieval evidence in the
  results artifact and has checkpoint recovery. Unit tests pass with `python -m pytest`.
- **PASS** Focused live q08/q11/q15 checks returned Rs. 12,000 per credit hour, Rule 1 in
  the superseded prospectus, and Rs. 12,000 per credit hour, respectively, with retrieved
  source citations. Evidence is in `docs/evidence/focused-q08-q11-q15.json`.
- **PASS** A specific retriever filter for the 100%-attendance clause query resolves q10;
  a live focused call and final full run returned clause 1.21 with the page-10 citation.
  q07's section filter was live-verified against Student Handbook page 60. q12 remains
  labeled `6. Generative AI and Assessments`, as supported by the retrieved passage.
- **IN PROGRESS** `eval/baseline.json` reflects the last complete run and passed numeric
  gates, but it must be regenerated after q09's live repair and a fresh 18-question run.
- **PASS with no regression observed** Four API modes were run one at a time against the same
  five-question subset, with a successful rollout and normal-mode restore after each. Each
  result is saved in `eval/failure-results/`; all retained recall@5 0.75, citations 3/3,
  abstention 1/1, and expected values 2/2. The small subset did not expose a fault, which is
  recorded without claiming the modes are harmless. Evidence: `docs/evidence/20261111-failure-mode-runs.txt`.
- **KNOWN FAILURE** Manual review found q09's false abstention, in addition to q18's retrieval
  miss. A verbatim evidence recovery with regression tests is in the working tree; live
  verification and full evaluation rerun are blocked by the zero-free-space C: drive and
  Minikube/Docker timeouts. See `docs/MANUAL-STEPS.md`.

## CI/CD, engineering notes, and submission (PDF sections 6-10)

- **PASS** CI/CD workflow definitions cover lint/type checks, coverage tests, strict
  manifests, image builds and scan, fixture e2e evaluation, SHA-tagged publishing, and
  ephemeral deployment smoke test. Every publishing/deploy job is gated with `needs:`;
  workflow permissions are least-privilege and actions version-pinned.
- **PASS** Makefile, CI and CD test invocations use `python -m pytest`.
- **PASS (focused)** Ruff passes; API answer/retriever tests pass (30), indexer tests pass
  (11), eval tests pass (7), and all four Kustomize overlays build. The combined Windows
  pytest invocation stalled; the focused suites complete. API/indexer mypy passed earlier,
  before the latest q09 repair.
- **PASS** Four ADRs and architecture, corpus, pipeline, failure, engineering, and AI-use
  documentation exist; update measured values after actual runs.
- **STUDENT ACTION** Both partners review AI disclosure and add any other AI tools used.
- **STUDENT ACTION** Write the personal >1-hour failure reflection from real team notes;
  do not use invented content. Placeholder is in `docs/ENGINEERING-NOTES.md`.
- **STUDENT ACTION** Configure Docker Hub Actions secrets; configure `main` branch
  protection with PR, one approval, and required CI; capture real protected-branch,
  blocked-merge, and green-merge screenshots.
- **PASS with warnings** Latest checker run reported 166 pass, 4 warnings, 0 failures;
  rerun after the final q09 full evaluation and documentation update.
- **STUDENT ACTION** Push only `dev`, open dev-to-main PR, obtain required review/checks,
  and submit repository, successful CD run, Docker Hub SHA image links, and committed
  results/baseline on Google Classroom.

## Remaining work

1. Student frees C: space and restarts Docker Desktop; verify Minikube and Ollama connectivity.
2. Live-check the q09 false-abstention repair, rerun all 18 questions, and regenerate the
   accepted baseline/results artifacts.
3. Refresh docs/evidence, rerun checks and submission checker, commit on `dev`, and push
   only `origin/dev` if GitHub authentication succeeds.
