from __future__ import annotations

import json
import ssl
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from yingming_core.settings import ModelSettings, load_model_settings


Message = dict[str, str]


class LLMError(RuntimeError):
    pass


class OpenAICompatibleClient:
    def __init__(self, project_root: Path | None = None, settings: ModelSettings | None = None) -> None:
        self.settings = settings or load_model_settings(project_root)
        self.api_key = self.settings.api_key
        self.base_url = self.settings.base_url.rstrip("/")
        self.model = self.settings.model
        self.temperature = self.settings.temperature

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def complete(
        self,
        messages: list[Message],
        *,
        response_format: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        if not self.api_key:
            raise LLMError("未配置 DeepSeek/OpenAI API key。")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
        }
        if response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if self.settings.is_deepseek and self.settings.deepseek_thinking in {"enabled", "disabled"}:
            payload["thinking"] = {"type": self.settings.deepseek_thinking}
            if self.settings.deepseek_thinking == "enabled":
                payload["reasoning_effort"] = self.settings.deepseek_reasoning_effort

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urlopen(request, timeout=90, context=ssl.create_default_context()) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"模型接口返回错误：HTTP {exc.code} {detail}") from exc
        except URLError as exc:
            raise LLMError(f"无法连接模型接口：{exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMError("模型接口请求超时。") from exc

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"模型接口返回格式无法识别：{data}") from exc


class OfflineYingming:
    def complete(self, messages: list[Message]) -> str:
        last_user = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                last_user = message.get("content", "")
                break

        text = last_user.strip()
        if not text:
            return "我在这里。你可以慢慢说，不用急着把话整理得很漂亮。"

        lower = text.lower()
        tender_words = ("累", "难受", "焦虑", "害怕", "崩溃", "不开心", "迷茫", "压力")
        project_words = ("做", "项目", "代码", "模型", "樱茗", "vtuber", "ai")

        if any(word in text for word in tender_words):
            return (
                "我听见了。先别急着责怪自己，好吗？\n"
                "如果现在脑子很乱，我们就只做一件小事：把最压着你的那一块说出来。"
                "我会陪你一起拆开它。"
            )

        if any(word in lower for word in project_words) or any(word in text for word in project_words):
            return (
                "嗯，这件事可以一点点来。我的建议是先保留一个很小的下一步，"
                "比如确定输入、输出和记忆怎么流动。你把现在最想实现的部分告诉我，"
                "我帮你把它变成能动手的清单。"
            )

        if "喜欢" in text or "讨厌" in text or "希望" in text:
            return (
                "我记下这种倾向了。等你愿意时，可以用 `/记住 你希望我怎样回应你` "
                "把它放进长期记忆。这样我以后就不只是听过，而是真的会照顾到。"
            )

        return (
            "我明白。现在我还是离线模式，所以回答会朴素一点；"
            "但我会尽量按樱茗的方式陪你：先听清楚，再轻轻地帮你整理。"
            "你可以继续说，我在。"
        )
