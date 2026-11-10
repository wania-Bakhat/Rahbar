# Ingestion, retrieval and evaluation

## End-to-end flow

`corpus/sources.yaml` defines eight official PDF sources and their versions. Run `make fetch` to download them and create `corpus/raw/_index.json`; the raw directory is intentionally gitignored. The Kubernetes indexer Job reads that manifest, extracts PDFs page by page, OCRs pages with no text layer using Tesseract/Poppler, removes repeated edge headers/footers and isolated page numbers, and chunks by headings, paragraphs and sentences. Each chunk preserves source, section, 1-based page, version and superseded metadata. It is embedded using the configured embedding model and replaces the Chroma collection. The API retrieves top-k passages, filters superseded content for current-policy questions, checks context sufficiency, builds a grounded prompt, calls the configured LLM and returns citations drawn from retrieved source/section/page metadata.

The deployment pins Chroma `1.0.12`. Its current server image persists to `/data`; the StatefulSet mounts its claim there and gives the non-root process a writable `/tmp` home/config path while keeping the container root filesystem read-only. `enableServiceLinks: false` prevents Kubernetes' generated `CHROMA_PORT=tcp://...` variable from colliding with Chroma's numeric `CHROMA_PORT` configuration. The indexer and API both need Ollama egress for `nomic-embed-text`; the Windows Minikube host IP is recorded in the ConfigMap URL and both narrowly scoped NetworkPolicy rules. `scripts/set_ollama_network_ip.sh` updates them together when that host route changes. API output is schema-validated: malformed output gets one retry, and citation/grounding validation failures can use a verbatim sentence from a directly matching retrieved passage with that passage's citation; tuition-per-credit answers and named historical rule headings also receive a narrow evidence check to prevent omitted or miscopied values.

The extraction audit counted 280 source pages, with 41 lacking a text layer. Thus OCR is necessary for full corpus coverage. A PDF character-boundary scan found text-layer characters outside visible page bounds in 29 Academic Rules Handbook pages and 58 Student Handbook pages; the other six PDFs had none. For example, page 25 of the Academic Rules Handbook visibly contains rules 5.7–5.13, while its unbounded text extraction also included clipped rules 5.1–5.6. Extraction now crops text to the visible page before cleaning and chunking. The audit details are in `docs/evidence/pdf-visible-boundary-audit.json`; this check concerns text geometry, not a manual verification of all OCR wording.

### Table extraction example

In `prospectus-fee-information-2026.pdf`, page 1, the ordinary `pdfplumber` page-text output is in reading order across a multi-column page. It interleaves prose under `1. Admission Fee` with the right-hand `5. Miscellaneous Fees` rows:

| Stage | Extracted text |
| --- | --- |
| Before, plain page text | `1. Admission Fee Admission Fee of Rs. 30,000 is Additional Transcript Fee Rs. 300` |
| Structured table row added by the indexer | `Table row: Semester Freeze Fee (within two weeks of start of classes) | Rs. | 2,000` |

The indexer appends bounded rows from `pdfplumber`'s separate `extract_tables()` result to the page text so chunking preserves the row-to-value relationship. It skips oversized pseudo-rows that represent a whole multi-column page, and keeps the original page number for citations. For `prospectus-fee-information-2026.pdf`, the extractor also splits the page at the observed column boundary, emitting the left fee policy before the right miscellaneous-fee table. This prevents the Rs. 300 certificate fee from being associated with the tuition-per-credit passage. A regression test verifies left/right ordering and the page's real Rs. 12,000 tuition value. The source page remains authoritative; OCR accuracy and unusual table layouts still require review. The extraction function is `indexer/pipeline/extract.py`.

## Chunk configuration and measured tuning

The indexer default is 400 whitespace-delimited tokens with a 50-token overlap. A token is one non-empty unit returned by Python `str.split()`; this is a documented, reproducible whitespace tokenizer, not Ollama's internal subword tokenizer. The tuning utility evaluates three configurations against the same 18 golden relevance pairs using recall@3 and recall@5.

| Whitespace-token size | Whitespace-token overlap | Recall@3 | Recall@5 | Chunks | Measurement status |
| ---: | ---: | ---: | ---: | ---: | --- |
| 200 | 25 | 0.875 | 0.875 | 1,172 | Measured on the full corpus and 18-question golden set |
| 400 | 50 | 0.875 | 0.875 | 1,029 | Measured; retained as the middle-size configuration, with no recall loss or gain in this run |
| 600 | 75 | 0.875 | 0.875 | 998 | Measured on the full corpus and 18-question golden set |

All three configurations returned identical recall in this run, so these measurements do not justify claiming that one improves retrieval. We retained 400:50 as the middle-size setting; it has fewer chunks than 200:25 and avoids shrinking to the largest chunks. The Job printed all measurements, then failed while serializing JSON because `/corpus` was outside its `/workspace` repository. The exact table and failure are preserved in `docs/evidence/chunk-tuning-job-stdout.txt`; `eval/chunk-tuning-results.json` records those values and that provenance. The serializer now supports mounted paths outside the repository, with regression tests.

The cleaner collapses whitespace, strips repeating edge lines (only when repeated at page edges), and drops isolated page-number lines at page edges. It protects numbered clauses from repeated-header removal, since those lines carry exact policy meaning. It intentionally does not remove arbitrary body sentences or headings. At section boundaries the chunker emits any newly added content even when it is shorter than the overlap; only a tail that exactly duplicates the previous chunk is suppressed. A page's original 1-based number is retained for citations.

The embedding pin is `EMBED_MODEL=nomic-embed-text` in `k8s/base/configmap.yaml`, consumed by both the API and indexer. The successful extraction-corrected Job `indexer-clipped2` finished at 2026-11-08 15:38:58 UTC, publishing 1,029 chunks in 839.7 seconds. Its output is saved in `docs/evidence/20261108-indexer-clipped2.txt`. A real `/api/embed` request returned a 768-dimensional vector for this model. The Job reports the count; the model endpoint check reports the dimension. The lower count than the preceding 1,148-chunk index follows cropping hidden out-of-page PDF text before chunking; it does not indicate missing visible pages.

Run `python eval/tune_chunking.py --help` for supported options. The cluster Job used the same corpus snapshot, Ollama embedding pin and golden file for all three isolated temporary Chroma collections. Its Job start time, corpus fingerprint and stdout provenance are in `eval/chunk-tuning-results.json` and `docs/evidence/chunk-tuning-job-stdout.txt`. Select based on retrieval results and inspect citation page/section quality; do not choose from chunk counts alone.

## Evaluation and regression gate

`eval/golden.yaml` is the assignment evaluation set. Each answerable question lists exact `(source, section)` relevance pairs; must-abstain questions have no relevant pairs and set `must_abstain: true`. It includes two questions whose expected attendance rule numbers differ between the current handbook and the superseded short prospectus version. `eval/run_eval.py` reports recall@3 and recall@5, recall by type, citation validity (source, section and page must match a retrieved passage), expected-value accuracy, and must-abstain correctness. Exact expected terms are checked in claim text after inline citations are removed. `eval/results.json` retains every question, response and retrieved passage for manual generation review alongside the aggregate metrics. The baseline gate permits no more than a 0.05 absolute recall@5 reduction, requires at least 0.95 citation validity, and fails when an expected value is absent or a must-abstain answer is grounded. A healthy baseline and result must be produced by a real API run before they can be committed.

## Semantic-cache threshold experiment

The configured similarity threshold is 0.95. `eval/cache-threshold-pairs.yaml` records labeled same-answer paraphrases and different-answer near-neighbors. The measured run in `eval/cache-threshold-results.json` used `nomic-embed-text`. Thresholds 0.85 and 0.90 each falsely merged the regular-course and summer-course attendance pair; 0.95 had zero false hits and is the lowest tested threshold with zero false hits. At 0.95, however, neither of the two same-answer paraphrases crossed the threshold, so the setting is conservative and misses paraphrase reuse on this small set.

| Threshold | False hits | Test status |
| ---: | ---: | --- |
| 0.85 | `regular-vs-summer-attendance` | 1/2 same-answer pairs hit |
| 0.90 | `regular-vs-summer-attendance` | 1/2 same-answer pairs hit |
| 0.95 | none | 0/2 same-answer pairs hit; lowest tested with zero false hits |

## Storage amplification

The assignment's 150/120 example means a 1.25x chunk-storage amplification: the 30-token overlap adds 25% over the 120-token source span. For this configuration, 50/400 is also 0.125 or 12.5% nominal overlap relative to chunk capacity. Actual corpus-wide amplification depends on section boundaries and short final chunks, and must be calculated using the same whitespace tokenizer over cleaned source text and stored chunk text. That corpus measurement is pending; the ratios above are configuration arithmetic, not a measured corpus statistic.

## Cache and index refresh

Only the API connects to Redis, as required by the PDF NetworkPolicy. An index write builds and verifies a uniquely named Chroma collection while the catalog still points at the previous complete generation. It then updates the catalog metadata with the new active collection and `index_generation`; API readers resolve the pointer on each request. The active and immediately previous collections are retained so in-flight reads finish and a prior index remains available. On a request, the API reads the generation and switches its Redis key namespace when it changes. Old cache keys become unreachable and expire by TTL; the indexer does not access Redis or flush keys. This keeps cache invalidation compatible with the API-only Redis ingress rule.
