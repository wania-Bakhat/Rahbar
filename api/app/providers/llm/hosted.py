"""Hosted free-tier provider (Groq, Google AI Studio, OpenRouter). Yours to build.

The key arrives as LLM_API_KEY from a Kubernetes Secret created on the command
line. It never appears in a file you commit, and never in a log line.
"""

from __future__ import annotations

import httpx

from ...config import Settings
from ...schemas import Answer, Passage
from ...telemetry import record_token_usage
from ._common import build_messages, effective_temperature, parse_answer


class HostedProvider:
    name = "hosted"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings   # hosted_base_url, llm_model, llm_api_key, temperature

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        base_url = self.settings.hosted_base_url.rstrip("/")
        if not base_url:
            raise RuntimeError("HOSTED_BASE_URL must be set when LLM_PROVIDER=hosted")
        if not self.settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY must be set when LLM_PROVIDER=hosted")
        endpoint = (base_url if base_url.endswith("/chat/completions")
                    else f"{base_url}/chat/completions")
        payload = {
            "model": self.settings.llm_model,
            "messages": build_messages(question, passages, self.settings.failure_mode),
            "temperature": effective_temperature(self.settings),
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        try:
            response = httpx.post(endpoint, json=payload, headers=headers,
                                  timeout=httpx.Timeout(180.0, connect=15.0))
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Do not include request headers or settings here; they may contain secrets.
            raise RuntimeError(f"Hosted chat request failed: {exc}") from exc

        usage = body.get("usage") or {}
        record_token_usage(usage.get("prompt_tokens"), usage.get("completion_tokens"))

        choices = body.get("choices") or []
        if not choices:
            raise RuntimeError("Hosted chat API returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError("Hosted chat API returned no message content")
        return parse_answer(content)
