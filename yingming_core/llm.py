from __future__ import annotations

import json
import shutil
import ssl
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from yingming_core.settings import ModelSettings, load_model_settings


Message = dict[str, str]


class LLMError(RuntimeError):
    pass


def friendly_llm_error(error: BaseException | str) -> str:
    text = str(error).strip()
    lower = text.lower()
    if "未配置" in text or "api key" in lower and "未配置" in text:
        return "还没有保存 API Key。打开“连接”填入 DeepSeek API Key 后再试。"
    if "401" in lower or "unauthorized" in lower:
        return "API Key 没通过验证，可能填错、失效，或复制时多了空格。"
    if "402" in lower or "quota" in lower or "balance" in lower:
        return "账号额度或余额可能不足，DeepSeek 那边拒绝了这次请求。"
    if "404" in lower and "model" in lower:
        return "模型名可能不可用。可以点“连接”里的“DeepSeek 默认”恢复默认模型后再试。"
    if "429" in lower or "rate limit" in lower:
        return "请求太频繁了，DeepSeek 暂时限流。稍等一会儿再发就好。"
    if "timeout" in lower or "timed out" in lower or "超时" in text:
        return "连接 DeepSeek 超时了，可能是网络慢、代理不稳，或服务端一时没响应。"
    if "ssl" in lower or "unexpected_eof" in lower or "eof occurred" in lower or "protocol" in lower:
        return "连接 DeepSeek 时网络/代理提前断开了（SSL 连接中断）。可以稍后重试，或检查代理、防火墙和 Base URL。"
    if "无法连接" in text or "urlopen" in lower or "connection" in lower:
        return "暂时连不上 DeepSeek。可以检查网络、代理、防火墙，或打开“连接”测试一下。"
    if text:
        return f"模型接口暂时不可用：{clip_text(text, 120)}"
    return "模型接口暂时不可用，但本地备用回复还能继续陪你。"


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
                "Accept": "application/json",
                "User-Agent": "YingmingPet/0.1",
            },
        )

        data = self._complete_with_urllib(request)

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"模型接口返回格式无法识别：{data}") from exc

    def _complete_with_urllib(self, request: Request) -> dict[str, Any]:
        last_error: LLMError | None = None
        for attempt in range(2):
            try:
                with urlopen(request, timeout=90, context=ssl.create_default_context()) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise LLMError(f"模型接口返回错误：HTTP {exc.code} {detail}") from exc
            except TimeoutError as exc:
                last_error = LLMError("模型接口请求超时。")
                if attempt == 0:
                    time.sleep(0.6)
                    continue
                raise last_error from exc
            except ssl.SSLError as exc:
                last_error = LLMError(f"无法连接模型接口：{exc}")
                if attempt == 0:
                    time.sleep(0.6)
                    continue
            except URLError as exc:
                last_error = LLMError(f"无法连接模型接口：{exc.reason}")
                if attempt == 0:
                    time.sleep(0.6)
                    continue

        if last_error is not None:
            try:
                return self._complete_with_curl(request)
            except LLMError as curl_error:
                raise curl_error from last_error
        raise LLMError("模型接口请求失败。")

    def _complete_with_curl(self, request: Request) -> dict[str, Any]:
        curl_path = shutil.which("curl.exe") or shutil.which("curl")
        if not curl_path:
            raise LLMError("模型接口请求失败，且本机没有可用的 curl。")

        body = bytes(request.data or b"")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as temp_file:
            temp_file.write(body)
            temp_path = temp_file.name

        try:
            completed = subprocess.run(
                [
                    curl_path,
                    "-sS",
                    "--connect-timeout",
                    "15",
                    "--max-time",
                    "90",
                    "-o",
                    "-",
                    "-w",
                    "\nYINGMING_HTTP_STATUS:%{http_code}",
                    "-H",
                    "Content-Type: application/json",
                    "-H",
                    f"Authorization: Bearer {self.api_key}",
                    "--data-binary",
                    f"@{temp_path}",
                    request.full_url,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

        output = completed.stdout.strip()
        error_output = completed.stderr.strip()
        if completed.returncode != 0:
            raise LLMError(f"无法连接模型接口：{error_output or output or 'curl 请求失败'}")

        marker = "\nYINGMING_HTTP_STATUS:"
        if marker not in output:
            raise LLMError(f"模型接口返回格式无法识别：{output or error_output}")
        body_text, status_text = output.rsplit(marker, 1)
        try:
            status = int(status_text.strip())
        except ValueError as exc:
            raise LLMError(f"模型接口返回状态无法识别：{status_text}") from exc
        if status >= 400:
            raise LLMError(f"模型接口返回错误：HTTP {status} {body_text}")

        try:
            return json.loads(body_text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"模型接口返回格式无法识别：{body_text}") from exc


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
            "我明白。先把你这句话放稳一点："
            "我会先听清楚，再轻轻地帮你整理。你可以继续说，我在。"
        )


def clip_text(text: str, limit: int) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "..."
