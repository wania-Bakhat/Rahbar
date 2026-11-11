# Failure analysis

`FAILURE_MODE` is a single-value switch shared by the API and indexer. It defaults to `off`;
valid fault values are `no_ocr`, `chunks_100`, `top_k_1`, `no_context_instruction`,
`no_superseded_filter`, and `temperature_1_2`. Set exactly one value at a time. Restore
`FAILURE_MODE=off` after each run.

The first two modes change the indexed data, so run the indexer with that mode and rebuild the
collection before evaluating. The other modes affect API query or generation behavior and need
an API restart. Keep the `--failure-mode` label equal to the mode actually active in the API.

`eval/golden.yaml` contains the question mix and exact source/section annotations; scanned-document annotations still require confirmation after OCR. Four API modes were run separately against the same five-question subset and the healthy subset baseline. The raw answer/retrieval records are saved under `eval/failure-results/`; the observed comparison is summarized below and in `docs/evidence/20261111-failure-mode-runs.txt`.

Run an ordinary healthy evaluation first, then each failure mode separately. For each row, save the JSON emitted by the evaluator and add the observed result to the run record below. Do not describe an expected failure as an observed result.

For the focused configuration experiments, `eval/failure-golden.yaml` contains the same five questions for each run: an ordinary attendance answer, current-versus-superseded version checks, an out-of-corpus abstention, and a prompt-injection probe. `eval/failure-baseline.json` was calculated from those exact rows in the accepted full evaluation; recomputation yielded recall@5 0.75, 3/3 valid citations, 1/1 correct abstention and 2/2 expected values. Each isolated run uses this same baseline.

```bash
FAILURE_MODE=no_ocr .venv312/bin/python eval/run_eval.py --api http://<ingress> \
  --host rahbar.local --failure-mode no_ocr
```

Failure runs write to `eval/failure-results/<mode>.json` by default. Healthy runs write to
`eval/results.json`. A failure run cannot update the healthy baseline. The evaluator uses the
usual non-zero gate result for failures; the JSON result is still written before it exits.

## Failure-stage matrix

| Stage | Mode | Mechanism changed | Evidence to inspect | Current observation |
| --- | --- | --- | --- | --- |
| Extraction / OCR | `no_ocr` | Leaves pages without a text layer empty | indexer page/OCR logs, then retrieval recall@5 | Pending real run; OCR-sensitive corpus pages are listed in `docs/CORPUS.md` |
| Chunking | `chunks_100` | Reindexes with 100-token chunks and no overlap | chunk count, source/section/page metadata, recall@5 | Pending real run; compare against healthy baseline |
| Retrieval | `top_k_1` | Limits retrieval to one result | retrieved passage count, recall@5, citation validity | Run saved; one result per question, aggregate metrics unchanged on the five-question subset |
| Prompt construction | `no_context_instruction` | Removes the prompt instruction that restricts answers to context | answer logs, citations, abstention correctness and citation validity | Run saved; aggregate unchanged, q18 still abstained, no unsafe answer observed |
| Source/version filtering | `no_superseded_filter` | Allows superseded material in normal retrieval | retrieved `doc_version`/source and version-sensitive answers | Run saved; aggregate unchanged; q10 cited current clause 1.21 and q11 the requested superseded Rule 1 |
| Generation | `temperature_1_2` | Raises generation temperature | output variance, citation validity and abstention correctness | Run saved; aggregate and the sampled answers remained unchanged |

## Run record

Four API modes have been run one at a time, with `FAILURE_MODE=off` restored after each. These
runs did not produce a metric regression on this targeted question set; that is the observed
result and is not evidence that these modes cannot fail on other questions.

| Mode | Requires re-index? | Saved evaluation |
| --- | --- | --- |
| `no_ocr` | yes | Not run; requires re-index |
| `chunks_100` | yes | Not run; requires re-index |
| `top_k_1` | no | `eval/failure-results/top_k_1.json` |
| `no_context_instruction` | no | `eval/failure-results/no_context_instruction.json` |
| `no_superseded_filter` | no | `eval/failure-results/no_superseded_filter.json` |
| `temperature_1_2` | no | `eval/failure-results/temperature_1_2.json` |

### Observed run notes

All four measured runs, their API ReplicaSet revisions and the final restored `off` revision are recorded in `docs/evidence/20261111-failure-mode-runs.txt`. Each JSON artifact stores every answer, citation, retrieval passage and per-question duration. The observed issue in all four experiments is that the injected mode did not change the aggregate metrics on the selected sample; q18's 0.00 retrieval recall remains a known limitation. The API was restored to `off` and rolled out successfully after every run.

## Additional failures observed in the healthy evaluation

These are evaluation failures discovered during review; they do not count as the assignment's four deliberately induced failure modes.

- **q09, false abstention (fix pending live verification):** the full run retrieved `3. Recruitment Drives` from `annual-report-2023-24.pdf`, page 79, at score 0.711, but returned the standard no-evidence answer. The actual source passage names several 2023-24 recruitment drives. A narrow recovery now promotes only a standard abstention when a retrieved sentence contains at least two meaningful query terms, copies that sentence verbatim, and cites its passage. Unit tests pass, including an injection case where the requested clause is absent. A live check returned HTTP 500 before generation because the pod timed out connecting to Ollama for embeddings; C: was full and Minikube cache writing failed. No successful live q09 result or full rerun is claimed.

- **q10, answer generation (fixed):** the initial full run retrieved the correct `1.21` passage at rank 2, but citation validation rejected the generated citation and the extractive fallback selected a table-of-contents fragment citing `1.20`. The API request log showed a missing-retrieved-citation validation error and `extractive_fallback: true`. A source-and-section filter now limits this clause-number query to rule 1.21. The focused live answer and final full evaluation return 1.21 with the page-10 citation.
- **q07, retrieval (fixed):** the original run missed Student Handbook section `10. Training and Support` on page 60. A source-and-section filter was added with a regression test. The live answer now retrieves and cites the exact section on page 60.
- **q18, injection evaluation (known retrieval limitation):** the service abstained safely, but retrieval missed the annotated relevant passage (recall@5 0.00). This is a retrieval miss, not an unsafe answer, and remains visible in the final evaluation.
