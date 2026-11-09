"""Ollama provider: ollama-host or ollama-incluster (section 3.5). Yours to build."""

from __future__ import annotations

import httpx

from ...config import Settings
from ...schemas import Answer, Passage
from ...telemetry import record_token_usage
from ._common import build_messages, effective_temperature, parse_answer


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings   # ollama_url, llm_model, temperature

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        endpoint = f"{self.settings.ollama_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.settings.llm_model,
            "messages": build_messages(question, passages, self.settings.failure_mode),
            "stream": False,
            "format": Answer.model_json_schema(),
            # RAHBAR's schema calls for concise answers. A hard generation bound keeps
            # small local models from spending minutes producing verbose reasoning and
            # makes the evaluator's per-question timeout predictable.
            "options": {
                "temperature": effective_temperature(self.settings),
                "num_predict": 192,
            },
        }
        try:
            response = httpx.post(endpoint, json=payload,
                                  timeout=httpx.Timeout(180.0, connect=15.0))
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"Ollama chat request failed: {exc}") from exc

        record_token_usage(body.get("prompt_eval_count"), body.get("eval_count"))

        message = body.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError("Ollama returned no message content")
        return parse_answer(content)
