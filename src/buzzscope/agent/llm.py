"""Thin LLM client layer: one real implementation (OpenAI) + a scripted fake for tests."""

from __future__ import annotations

import json
from typing import Any, Protocol

from buzzscope.models import Usage


class LLMClient(Protocol):
    usage: Usage
    model: str

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        """Return an OpenAI-style assistant message: {"role", "content", "tool_calls"?}."""
        ...


class OpenAIClient:
    def __init__(self, api_key: str, model: str):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self.model = model
        self.usage = Usage()

    def chat(self, messages, tools=None, tool_choice=None, json_mode=False):
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["parallel_tool_calls"] = True
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._client.chat.completions.create(**kwargs)
        if resp.usage:
            self.usage.add(
                Usage(
                    llm_calls=1,
                    input_tokens=resp.usage.prompt_tokens,
                    output_tokens=resp.usage.completion_tokens,
                )
            )
        msg = resp.choices[0].message
        out: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        return out


class ScriptedLLM:
    """Replays pre-written responses. Lets us test the agent loop without an API key.

    Each script item is either a string (plain reply) or a list of (tool_name, args) tool calls.
    """

    def __init__(self, script: list[Any]):
        self.script = list(script)
        self.model = "scripted"
        self.usage = Usage()
        self.seen: list[list[dict[str, Any]]] = []

    def chat(self, messages, tools=None, tool_choice=None, json_mode=False):
        self.seen.append(list(messages))
        self.usage.add(Usage(llm_calls=1))
        item = self.script.pop(0) if self.script else "（腳本已結束）"
        if isinstance(item, str):
            return {"role": "assistant", "content": item}
        calls = [
            {
                "id": f"call_{len(self.seen)}_{i}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
            }
            for i, (name, args) in enumerate(item)
        ]
        return {"role": "assistant", "content": "", "tool_calls": calls}


def parse_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from a model reply, tolerating ```json fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :]
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])
