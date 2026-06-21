from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from yingming_core.dialogue_state import detect_dialogue_state
from yingming_core.greetings import current_greeting
from yingming_core.llm import LLMError, Message, OfflineYingming, OpenAICompatibleClient
from yingming_core.memory import MemoryStore
from yingming_core.memory_retrieval import format_memory_context, retrieve_relevant_memories
from yingming_core.topic_state import detect_topic_state


HELP_TEXT = """可用指令：
/退出       结束聊天
/记住 内容  写入长期记忆
/回忆       查看长期记忆
/画像       查看你的画像
/帮助       查看这份帮助

如果终端对中文输入不友好，也可以用：
/exit, /remember 内容, /memory, /profile, /help
"""


OFFLINE_HISTORY_MARKERS = (
    "现在我还是离线模式",
    "现在还没有配置模型 API",
    "现在还是离线模式",
    "模型那边暂时没有接上",
)


def run_chat(project_root: Path) -> None:
    persona_path = project_root / "personas" / "yingming.md"
    profile_path = project_root / "data" / "profile.md"
    history_path = project_root / "data" / "chat_history.jsonl"
    memory = MemoryStore(project_root / "data" / "memory.json")

    persona = persona_path.read_text(encoding="utf-8")
    profile = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
    history_path.parent.mkdir(parents=True, exist_ok=True)

    client = OpenAICompatibleClient(project_root)
    offline = OfflineYingming()
    recent_messages = load_recent_history(history_path, limit=12, drop_offline_placeholders=client.available)

    print(f"樱茗：{current_greeting()}。我在这里。输入 /帮助 可以看指令，输入 /退出 就能结束。")
    if not client.available:
        print("樱茗：现在还没有配置模型 API，我会先用离线模式陪你试运行。")
    else:
        print(f"樱茗：已经接入 {client.settings.display_name}。")

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

        memory_data = memory.load()
        retrieved_memories = retrieve_relevant_memories(
            memory_data,
            user_text,
            recent_messages=recent_messages,
            profile_text=profile,
        )
        messages = build_messages(
            persona,
            profile,
            format_memory_context(memory_data, retrieved_memories),
            recent_messages,
            user_text,
            active_model=client.settings.display_name if client.available else "",
            dialogue_state_text=detect_dialogue_state(
                user_text,
                recent_messages,
                memory_data,
            ).as_prompt_text(),
            topic_state_text=detect_topic_state(recent_messages, user_text).as_prompt_text(),
        )
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
        recent_messages = load_recent_history(history_path, limit=12, drop_offline_placeholders=client.available)


def build_messages(
    persona: str,
    profile: str,
    memory_text: str,
    recent_messages: list[Message],
    user_text: str,
    active_model: str = "",
    dialogue_state_text: str = "",
    topic_state_text: str = "",
) -> list[Message]:
    system = "\n\n".join(
        part
        for part in [
            persona,
            "以下是已经确认的使用者画像：\n" + profile.strip() if profile.strip() else "",
            "以下是长期记忆与边界：\n" + memory_text if memory_text else "",
            (
                f"当前已经接入在线模型：{active_model}。"
                "不要自称处于离线模式，也不要说回答会因为离线而朴素。"
            )
            if active_model
            else "",
            current_time_context(),
            (
                "陪伴风格：你可以更像一个有真实相处感的 AI 女孩，有主动性、好奇心、"
                "细微情绪和自己的判断；但始终坦诚自己是 AI，不假装成人类、现实女友或唯一依靠。"
                "亲近要自然克制，有分寸地陪伴用户。"
            ),
            dialogue_state_text,
            topic_state_text,
            "请优先使用中文。回答自然、温柔、具体，不要长篇说教。",
        ]
        if part
    )
    return [{"role": "system", "content": system}, *recent_messages, {"role": "user", "content": user_text}]


def current_time_context() -> str:
    now = datetime.now().astimezone()
    weekdays = "一二三四五六日"
    offset = now.strftime("%z")
    if offset:
        offset_text = f"UTC{offset[:3]}:{offset[3:]}"
    else:
        offset_text = "本地时区"
    return (
        f"当前本机时间：{now.strftime('%Y-%m-%d %H:%M:%S')}（{offset_text}，星期{weekdays[now.weekday()]}）。"
        "如果用户询问今天、现在、今晚、昨天、明天或日期时间，必须以这条时间为准；"
        "不要凭模型记忆猜日期。"
    )


def load_recent_history(path: Path, limit: int, drop_offline_placeholders: bool = False) -> list[Message]:
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
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

    if drop_offline_placeholders:
        messages = drop_offline_placeholder_turns(messages)

    return messages[-limit:]


def drop_offline_placeholder_turns(messages: list[Message]) -> list[Message]:
    cleaned: list[Message] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        next_message = messages[index + 1] if index + 1 < len(messages) else None
        if (
            message.get("role") == "user"
            and next_message
            and next_message.get("role") == "assistant"
            and is_offline_placeholder(next_message.get("content", ""))
        ):
            index += 2
            continue
        if message.get("role") == "assistant" and is_offline_placeholder(message.get("content", "")):
            index += 1
            continue
        cleaned.append(message)
        index += 1
    return cleaned


def is_offline_placeholder(content: str) -> bool:
    return any(marker in content for marker in OFFLINE_HISTORY_MARKERS)


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
