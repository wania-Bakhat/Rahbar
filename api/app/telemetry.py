"""Prometheus instruments shared by middleware and the query pipeline."""

from prometheus_client import Counter, Gauge, Histogram

from .logjson import request_observation_var

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
LLM_PROMPT_TOKENS = Counter("rahbar_llm_prompt_tokens_total", "Provider-reported LLM input tokens")
LLM_COMPLETION_TOKENS = Counter(
    "rahbar_llm_completion_tokens_total", "Provider-reported LLM output tokens"
)


def record_token_usage(prompt_tokens: object, completion_tokens: object) -> None:
    """Record provider-reported token counts in Prometheus and request JSON logs."""
    prompt_count = _non_negative_int(prompt_tokens)
    completion_count = _non_negative_int(completion_tokens)
    if prompt_count is None and completion_count is None:
        return
    observation = request_observation_var.get()
    if prompt_count is not None:
        LLM_PROMPT_TOKENS.inc(prompt_count)
        if observation is not None:
            previous = observation.get("llm_prompt_tokens", 0)
            observation["llm_prompt_tokens"] = (
                (previous if isinstance(previous, int) else 0) + prompt_count
            )
    if completion_count is not None:
        LLM_COMPLETION_TOKENS.inc(completion_count)
        if observation is not None:
            previous = observation.get("llm_completion_tokens", 0)
            observation["llm_completion_tokens"] = (
                (previous if isinstance(previous, int) else 0) + completion_count
            )


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
