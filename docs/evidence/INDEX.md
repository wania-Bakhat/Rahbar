# Evidence index

Evidence files record observed outputs. A planned command or a placeholder is not proof.

| Requirement | Evidence | Status / note |
| --- | --- | --- |
| Full corpus publication after visible-page and fee-column extraction fixes | `20261108-indexer-clipped2.txt` | Real Job logs; 1,029 chunks; completed in 839.7 seconds |
| Fee extraction and tuition answer | `fee-table-api-check.json`, `focused-q08-q11-q15.json` | The prospectus states Rs. 12,000 per credit hour; the latter also checks q11 |
| PDF text-boundary audit | `pdf-visible-boundary-audit.json` | Geometry scan across source PDFs; not a manual OCR transcription review |
| NetworkPolicy allow/deny paths, including UI DNS | `20261108-network-policy.txt` | All expected checks passed with active route 192.168.127.254 |
| Indexer resource use | `20261108T111618Z-indexer-resource-samples.txt` | 25 real samples; sampled maxima only |
| API endpoints, HPA, pods and rollout | `20261108T113353Z-endpoints.txt`, `20261108T113353Z-hpa.txt`, `20261108T113353Z-pods.txt`, `20261108T113353Z-rollout.txt`, `20261108T113353Z-rollout-history.txt`, `20261108T113353Z-top-pods.txt` | Captured from Minikube |
| First full evaluation | `eval-full-run-before-q10-repair.json` | Diagnostic run with the pre-correction q12 label; not a baseline |
| Corrected full evaluation | `../../eval/results.json` | Complete 18-question run; recall@5 0.875, citations 15/15, abstention 2/2; q10 gate fails |
| Focused q10 live failure after API rebuild | `focused-q10-after-fix.json` | It still cites 1.20 while retrieved evidence includes 1.21; known failure |
| Cache-threshold measurements | `../../eval/cache-threshold-results.json` | Real six-pair run; 0.95 had zero false hits but 0/2 same-answer hits |
| Current live evaluation/answer behavior | `eval-diagnostic-before-source-filters.json`, `focused-q08-q11-q15.json` | Earlier diagnostics; do not substitute for the final rerun |
| q07 source section extraction | `../../corpus/raw/student-handbook-2026.pdf` | Local extraction of pages 60-61 produced section 10; retriever filter/test added, live check pending |
| Rollout undo and post-undo smoke test | — | Pending live demonstration |
| Deleted API pod recovery | — | Pending live demonstration |
| Embedding-pin mismatch and recovery | — | Pending live demonstration |
| Branch protection, blocked merge, passing merge state | `../MANUAL-STEPS.md` | Student must capture authentic GitHub screenshots |
| Chunk tuning output | — | Not produced; temporary tuning container could not be inspected after Docker became unavailable |
