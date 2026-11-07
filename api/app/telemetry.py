"""Prometheus instruments shared by middleware and the query pipeline."""

from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter("rahbar_requests_total", "HTTP requests", ["path", "status"])
LATENCY = Histogram(
    "rahbar_request_seconds",
    "HTTP request latency",
    ["path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
RETRIEVAL_LATENCY = Histogram(
    "rahbar_retrieval_seconds", "Query embedding and vector retrieval latency",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
GENERATION_LATENCY = Histogram(
    "rahbar_generation_seconds", "LLM generation and validation latency",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120),
)
CACHE_LOOKUPS = Counter("rahbar_cache_lookups_total", "Semantic cache lookups")
CACHE_HITS = Counter("rahbar_cache_hits_total", "Semantic cache hits")
CACHE_HIT_RATIO = Gauge("rahbar_cache_hit_ratio", "Cumulative semantic cache hit ratio")
ABSTENTIONS = Counter("rahbar_abstentions_total", "Answers that abstained")
FALLBACKS = Counter("rahbar_fallbacks_total", "Safe generation fallbacks")
