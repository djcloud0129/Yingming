from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from yingming_core.llm import LLMError, Message, OfflineYingming, OpenAICompatibleClient
from yingming_core.memory import MemoryStore


HELP_TEXT = """可用指令：
/退出       结束聊天
/记住 内容  写入长期记忆
/回忆       查看长期记忆
/画像       查看你的画像
/帮助       查看这份帮助

如果终端对中文输入不友好，也可以用：
/exit, /remember 内容, /memory, /profile, /help
"""


def run_chat(project_root: Path) -> None:
    persona_path = project_root / "personas" / "yingming.md"
    profile_path = project_root / "data" / "profile.md"
    history_path = project_root / "data" / "chat_history.jsonl"
    memory = MemoryStore(project_root / "data" / "memory.json")

    persona = persona_path.read_text(encoding="utf-8")
    profile = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
    history_path.parent.mkdir(parents=True, exist_ok=True)

    client = OpenAICompatibleClient()
    offline = OfflineYingming()
    recent_messages = load_recent_history(history_path, limit=12)

    print("樱茗：晚上好。我在这里。输入 /帮助 可以看指令，输入 /退出 就能结束。")
    if not client.available:
        print("樱茗：现在还没有配置模型 API，我会先用离线模式陪你试运行。")

    while True:
        try:
            user_text = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n樱茗：那今天先到这里。记得喝点水，慢慢来。")
            break

        if not user_text:
            continue

        if user_text in {"/退出", "/exit", "/quit"}:
            print("樱茗：嗯，我会把灯留着。下次见。")
            break

        if user_text in {"/帮助", "/help"}:
            print(HELP_TEXT)
            continue

        if user_text in {"/回忆", "/memory"}:
            print(memory.as_readable_text())
            continue

        if user_text in {"/画像", "/profile"}:
            print(profile_path.read_text(encoding="utf-8") if profile_path.exists() else "还没有画像。")
            continue

        remember_prefix = get_remember_prefix(user_text)
        if remember_prefix:
            item = memory.add(user_text.removeprefix(remember_prefix), category="manual", source="chat_command")
            print(f"樱茗：好，我记住了：{item.text}")
            continue

        messages = build_messages(persona, profile, memory.as_prompt_text(), recent_messages, user_text)
        try:
            reply = client.complete(messages) if client.available else offline.complete(messages)
        except LLMError as exc:
            reply = (
                "模型那边暂时没有接上，我先用自己的小纸条回答你。\n"
                f"接口信息：{exc}\n\n"
                f"{offline.complete(messages)}"
            )

        print(f"樱茗：{reply}")
        append_history(history_path, "user", user_text)
        append_history(history_path, "assistant", reply)
        recent_messages = load_recent_history(history_path, limit=12)


def build_messages(
    persona: str,
    profile: str,
    memory_text: str,
    recent_messages: list[Message],
    user_text: str,
) -> list[Message]:
    system = "\n\n".join(
        part
        for part in [
            persona,
            "以下是已经确认的使用者画像：\n" + profile.strip() if profile.strip() else "",
            "以下是长期记忆与边界：\n" + memory_text if memory_text else "",
            "请优先使用中文。回答自然、温柔、具体，不要长篇说教。",
        ]
        if part
    )
    return [{"role": "system", "content": system}, *recent_messages, {"role": "user", "content": user_text}]


def load_recent_history(path: Path, limit: int) -> list[Message]:
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    messages: list[Message] = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            messages.append({"role": role, "content": content})
    return messages


def append_history(path: Path, role: str, content: str) -> None:
    item = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "role": role,
        "content": content,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def get_remember_prefix(text: str) -> str:
    for prefix in ("/记住 ", "/remember "):
        if text.startswith(prefix):
            return prefix
    return ""
