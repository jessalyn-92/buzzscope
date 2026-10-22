"""A rule-based stand-in for the LLM, used only in tests.

It drives the *real* agent loop, tools, validation, and eval end-to-end without an API key:
it reads tool results from the message history and decides the next calls like a
(very literal) analyst would. It is not a substitute for the LLM — it just proves the
plumbing works and the tool outputs contain what an analyst needs.
"""

from __future__ import annotations

import json

from buzzscope.models import Usage


class PolicyLLM:
    def __init__(self, entity: str, bad_first_submit: bool = False):
        self.entity = entity
        self.model = "policy"
        self.usage = Usage()
        self.bad_first_submit = bad_first_submit
        self.phase = "start"
        self.spikes: list[dict] = []
        self.i = 0
        self.notes: dict[str, dict] = {}

    def _last_tool_results(self, messages):
        out = []
        for m in reversed(messages):
            if m.get("role") != "tool":
                break
            out.append(json.loads(m["content"]))
        return list(reversed(out))

    @staticmethod
    def _call(name, **args):
        return {
            "id": f"c{name}{len(json.dumps(args))}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
        }

    def chat(self, messages, tools=None, tool_choice=None, json_mode=False):
        self.usage.add(Usage(llm_calls=1))
        if json_mode:  # verifier
            return {"role": "assistant", "content": '{"supported": true, "reason": "證據文章內容與結論一致"}'}
        results = self._last_tool_results(messages)
        calls = []

        if self.phase == "start":
            calls = [self._call("get_overview"), self._call("detect_spikes")]
            self.phase = "spikes"
        elif self.phase == "spikes":
            self.spikes = results[1]["spikes"]
            self.phase = "terms"
        if self.phase == "terms":
            if self.i >= len(self.spikes):
                self.phase = "submit"
            else:
                s = self.spikes[self.i]
                calls = [self._call("compare_terms", start_date=s["start"], end_date=s["end"])]
                self.phase = "search"
        elif self.phase == "search":
            s = self.spikes[self.i]
            term = results[0]["distinctive_terms"][0]["term"]
            self.notes[s["peak_date"]] = {"term": term}
            calls = [
                self._call("search_posts", query=term, start_date=s["start"], end_date=s["end"], limit=3)
            ]
            self.phase = "read"
        elif self.phase == "read":
            s = self.spikes[self.i]
            ids = [p["id"] for p in results[0]["posts"]]
            calls = [self._call("read_posts", post_ids=ids)]
            self.phase = "judge"
        elif self.phase == "judge":
            s = self.spikes[self.i]
            posts = results[0]["posts"]
            about_entity = sum(self.entity in (p["title"] + p["content"]) for p in posts)
            push = sum(p["push"] for p in posts)
            boo = sum(p["boo"] for p in posts)
            self.notes[s["peak_date"]].update(
                ids=[p["id"] for p in posts],
                kind="event" if about_entity >= max(1, len(posts) // 2) else "unrelated",
                sentiment="positive" if push >= boo else "negative",
            )
            self.i += 1
            self.phase = "terms"
            return self.chat(messages, tools)  # same turn: move on to the next spike

        if self.phase == "submit":
            findings = [
                {
                    "spike_date": d,
                    "kind": n["kind"],
                    "cause": f"與「{n['term']}」相關的討論",
                    "sentiment": n["sentiment"],
                    "summary": "",
                    "evidence_post_ids": n["ids"],
                    "confidence": 0.7,
                }
                for d, n in self.notes.items()
            ]
            if self.bad_first_submit:
                self.bad_first_submit = False
                findings = findings[:-1] + [{**findings[-1], "evidence_post_ids": ["NOT-A-REAL-ID"]}]
            calls = [self._call("submit_findings", findings=findings, overall_summary="測試總結")]
        return {"role": "assistant", "content": "", "tool_calls": calls}
