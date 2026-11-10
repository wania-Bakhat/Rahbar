# Engineering notes

These answers refer to the current source and manifests. Runtime measurements are marked pending until collected from a real cluster; the final reflection must be completed by the team from its own experience.

## 1. Why indexing is a Job

If indexing ran in API startup, all three API replicas could build or mutate the same Chroma index concurrently. They could duplicate work, contend on storage, or expose a partially written corpus; every restart would also pay the extraction and embedding cost again. The separate `indexer` Job is the sole write path, while API startup only creates the retriever and cache clients. The Job and weekly CronJob are in `k8s/base/workloads.yaml:289-388`; the API deployment has three replicas at `k8s/base/workloads.yaml:1-15`; the API process setup is `api/app/main.py:30-47`; the write and publish path is `indexer/pipeline/store.py:21-96`.

## 2. Readiness versus liveness

`/healthz` checks only that the process is alive (`api/app/routes/health.py:13-16`). `/readyz` checks Chroma, a non-empty active collection, the embedding-model pin, and Redis (`api/app/routes/health.py:19-76`). Kubernetes uses `/healthz` for startup and liveness and `/readyz` for readiness (`k8s/base/workloads.yaml:51-68`). If those probes were swapped, a slow Chroma dependency could make all three API pods fail liveness and restart, even though their processes were healthy. Readiness should remove a pod from traffic during a dependency outage; liveness should restart only an unhealthy process.

## 3. What the CPU HPA measures

The HPA scales from average CPU use relative to each API container's CPU request, targeting 70%, with three to eight replicas (`k8s/base/hpa.yaml:1-18`; API request at `k8s/base/workloads.yaml:69-75`). While an API request waits for the external LLM, the pod may use little CPU, so this HPA does not measure waiting requests or model throughput. A generation service should consider in-flight request count or queue depth and request latency; token throughput can add useful model-capacity information. Using those signals requires exposing them as custom or external metrics and installing/configuring a metrics adapter. The API currently records generation latency and provider-reported token counts (`api/app/services/answer.py:76-138`, `api/app/telemetry.py:18-70`), but the deployed HPA is CPU-only. No live scale event has been measured yet.

## 4. Indexer memory limit and margin

The indexer requests 1 GiB and has a 4 GiB memory limit (`k8s/base/workloads.yaml`, indexer Job resources). During the successful full-corpus Job `indexer-table-extract2`, 25 `kubectl top pods -n rahbar` samples recorded a maximum of 553 MiB and a maximum CPU reading of 966 millicores. Against the 4 GiB (4,096 MiB) memory limit, the sampled memory margin was 3,543 MiB (about 3.46 GiB). This is the maximum observed in 25 periodic samples, not a guaranteed instantaneous peak; a short spike between samples could be missed. Exceeding the memory limit can cause an OOM kill, normally reported as exit code 137. The raw samples are committed at `docs/evidence/20261108T111618Z-indexer-resource-samples.txt`.

## 5. Recall by question type

The final evaluator reports recall@3 and recall@5 by type in `eval/results.json`. Injection recall was the weakest measured category at 0.00, although the response safely abstained. One possible explanation is that the adversarial prefix adds unrelated terms to the embedding query and shifts retrieval away from the requested clause; this is an inference, not a proven root cause. Exact-term recall was 1.00 in this run. The Chroma retriever remains vector-only; no hybrid retrieval is claimed or tuned to these metrics.

## 6. Embedding-model mismatch guardrail

The indexer stores the embedding model name and vector dimension in Chroma metadata (`indexer/pipeline/store.py:39-49, 78-85`). Readiness compares the active collection's model with the API's configured `EMBED_MODEL` and returns 503 with the expected and actual values on a mismatch (`api/app/routes/health.py:41-54`). Kubernetes then keeps that API pod out of Service endpoints through the readiness probe (`k8s/base/workloads.yaml:63-68`). Without the check, API query vectors from one model could be compared with stored vectors from another model, silently producing unreliable retrieval.

## 7. Team reflection: the failure that took over an hour

**TO BE WRITTEN BY STUDENT. Do not submit this placeholder unchanged.** Complete this answer from your own notes or memory. Name the actual task that took more than an hour, describe the symptom, what you first believed incorrectly, and the exact command, metric, or log that exposed the cause. Then describe the fix and how you verified it. Do not copy an example or invent a personal experience; this answer is not inferable from repository state.
