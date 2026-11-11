# Evidence index

Evidence files record observed outputs. A planned command or a placeholder is not proof.

| Requirement | Evidence | Status / note |
| --- | --- | --- |
| Full corpus publication after visible-page and fee-column extraction fixes | `20261108-indexer-clipped2.txt` | Real Job logs; 1,029 chunks; completed in 839.7 seconds |
| Final full-corpus reindex on restored cluster | `20261110-indexer-final.txt` | Real Job logs; 1,029 chunks; completed in 857.5 seconds |
| Fee extraction and tuition answer | `fee-table-api-check.json`, `focused-q08-q11-q15.json` | The prospectus states Rs. 12,000 per credit hour; the latter also checks q11 |
| PDF column-order spot-check | `20261111-layout-audit.txt` | Fee prospectus visual and extraction check; Academic Rules page 25 extraction follows visible clauses 5.7-5.13; annual report page 5 is single-column. Targeted sample, not all 280 pages |
| PDF text-boundary audit | `pdf-visible-boundary-audit.json` | Geometry scan across source PDFs; not a manual OCR transcription review |
| NetworkPolicy allow/deny paths, including UI DNS | `20261110-network-policy.txt` | All expected checks passed with active route 192.168.127.254 |
| Indexer resource use | `20261108T111618Z-indexer-resource-samples.txt` | 25 real samples; sampled maxima only |
| API endpoints, HPA, pods and rollout | `20261108T113353Z-endpoints.txt`, `20261108T113353Z-hpa.txt`, `20261108T113353Z-pods.txt`, `20261108T113353Z-rollout.txt`, `20261108T113353Z-rollout-history.txt`, `20261108T113353Z-top-pods.txt` | Captured from Minikube |
| First full evaluation | `eval-full-run-before-q10-repair.json` | Diagnostic run with the pre-correction q12 label; not a baseline |
| Latest complete full evaluation (baseline provisional) | `../../eval/results.json`, `../../eval/baseline.json` | Complete 18-question run; recall@5 0.9375, citations 14/14 emitted, must-abstain 2/2, expected values 7/7; q09 falsely abstained despite relevant retrieval |
| q09 live verification blocked | `20261111-q09-live-blocker.txt` | API failed while embedding due Ollama connect timeout; C: reported 0 free bytes and Minikube image loading could not write its cache |
| Focused q10 live fix | `focused-q10-live-filter.json` | Returns clause 1.21 with page-10 citation after exact-section filter |
| Cache-threshold measurements | `../../eval/cache-threshold-results.json` | Real six-pair run; 0.95 had zero false hits but 0/2 same-answer hits |
| Current live evaluation/answer behavior | `eval-diagnostic-before-source-filters.json`, `focused-q08-q11-q15.json` | Earlier diagnostics; do not substitute for the final rerun |
| q07 source section extraction and live answer | `../../corpus/raw/student-handbook-2026.pdf`, `focused-q07-live.json` | Returns section 10 on page 60 |
| Rollout undo and post-undo smoke test | `20261110-rollout-undo.txt` | Previous image rollout, undo, 3/3 ready, `/readyz` ready |
| Deleted API pod recovery | `20261110-pod-recovery.txt` | Replacement became ready; service returned to three endpoints |
| Embedding-pin mismatch and recovery | `20261110-embedding-pin-mismatch.txt` | HTTP 503 showed expected/actual mismatch; restored pin returned readiness |
| Four isolated API fault-mode measurements | `20261111-failure-mode-runs.txt`, `../../eval/failure-results/*.json` | All four modes were applied separately, the API returned to `off` afterward, and per-question output is saved. Metrics did not regress on this five-question sample |
| Branch protection, blocked merge, passing merge state | `../MANUAL-STEPS.md` | Student must capture authentic GitHub screenshots |
| Chunk tuning output and serializer error | `../../eval/chunk-tuning-results.json`, `chunk-tuning-job-stdout.txt` | All three real configurations completed; the Job printed measured results, then failed only during JSON path serialization. External mounted-path handling now has regression tests |
