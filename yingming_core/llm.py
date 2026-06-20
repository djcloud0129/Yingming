from __future__ import annotations

import json
import os
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


Message = dict[str, str]


class LLMError(RuntimeError):
    pass


class OpenAICompatibleClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("YINGMING_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("YINGMING_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("YINGMING_MODEL", "gpt-4o-mini")
        self.temperature = float(os.getenv("YINGMING_TEMPERATURE", "0.8"))

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def complete(self, messages: list[Message]) -> str:
        if not self.api_key:
            raise LLMError("未配置 YINGMING_API_KEY 或 OPENAI_API_KEY。")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
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

