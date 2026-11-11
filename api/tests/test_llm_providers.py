from __future__ import annotations

import json as jsonlib
from typing import Any

from prometheus_client import generate_latest

from app.config import Settings
from app.providers.llm import get_provider
from app.providers.llm.hosted import HostedProvider
from app.providers.llm.ollama import OllamaProvider
from app.providers.llm.stub import StubProvider
from app.schemas import Answer, Passage
from app.logjson import request_observation_var

_ANSWER = {
    "reasoning": "The passage states the attendance rule.",
    "answer": "Attendance is required.",
    "citations": [{"source": "rules.pdf", "section": "1 Attendance", "page": 2}],
    "answered_from_context": True,
    "confidence": "high",
}


class Response:
    def __init__(self, body: dict[str, Any]) -> None:
        self.body = body

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return self.body


def _passages() -> list[Passage]:
    return [Passage(chunk_id="c1", text="Attendance is required.", source="rules.pdf",
                    section="1 Attendance", page=2, score=0.9)]


def test_ollama_provider_uses_schema_format_and_validates_answer(monkeypatch) -> None:
    settings = Settings(ollama_url="http://ollama:11434", llm_model="llama-test",
                        temperature=0.2)
    provider = OllamaProvider(settings)
    captured: dict[str, Any] = {}
    observation: dict[str, object] = {}
    context_token = request_observation_var.set(observation)

    def fake_post(url: str, *, json: dict[str, Any], timeout: Any) -> Response:
        captured.update(url=url, payload=json)
        return Response({"prompt_eval_count": 21, "eval_count": 8,
                         "message": {"content": jsonlib.dumps(_ANSWER)}})

    monkeypatch.setattr("app.providers.llm.ollama.httpx.post", fake_post)
    answer = provider.generate("Attendance?", _passages())

    assert isinstance(answer, Answer)
    assert captured["url"] == "http://ollama:11434/api/chat"
    assert captured["payload"]["model"] == "llama-test"
    assert captured["payload"]["options"]["temperature"] == 0.2
    assert captured["payload"]["options"]["num_predict"] == 192
    assert captured["payload"]["format"]["properties"].keys() == _ANSWER.keys()
    messages = captured["payload"]["messages"]
    assert messages[0]["role"] == "system"
    assert "Answer only from the retrieved evidence" in messages[0]["content"]
    assert messages[1]["content"].index("[1]") < messages[1]["content"].index("Question:")
    assert observation["llm_prompt_tokens"] == 21
    assert observation["llm_completion_tokens"] == 8
    metrics = generate_latest().decode()
    assert "rahbar_llm_prompt_tokens_total 21.0" in metrics
    assert "rahbar_llm_completion_tokens_total 8.0" in metrics
    request_observation_var.reset(context_token)


def test_hosted_provider_uses_json_mode_and_secret_header(monkeypatch) -> None:
    settings = Settings(hosted_base_url="https://llm.example/v1", llm_api_key="test-secret",
                        llm_model="hosted-test")
    provider = HostedProvider(settings)
    captured: dict[str, Any] = {}
    observation: dict[str, object] = {}
    context_token = request_observation_var.set(observation)

    def fake_post(url: str, *, json: dict[str, Any], headers: dict[str, str], timeout: Any) -> Response:
        captured.update(url=url, payload=json, headers=headers)
        return Response({"usage": {"prompt_tokens": 18, "completion_tokens": 6},
                         "choices": [{"message": {
            "content": jsonlib.dumps(_ANSWER)
        }}]})

    monkeypatch.setattr("app.providers.llm.hosted.httpx.post", fake_post)
    answer = provider.generate("Attendance?", _passages())

    assert isinstance(answer, Answer)
    assert captured["url"] == "https://llm.example/v1/chat/completions"
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["headers"]["Authorization"] == "Bearer test-secret"
    assert observation["llm_prompt_tokens"] == 18
    assert observation["llm_completion_tokens"] == 6
    request_observation_var.reset(context_token)


def test_provider_selector_keeps_all_three_modes() -> None:
    assert isinstance(get_provider(Settings(llm_provider="stub")), StubProvider)
    assert isinstance(get_provider(Settings(llm_provider="ollama-host")), OllamaProvider)
    assert isinstance(get_provider(Settings(llm_provider="ollama-incluster")), OllamaProvider)
    assert isinstance(get_provider(Settings(llm_provider="hosted")), HostedProvider)
