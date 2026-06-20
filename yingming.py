from __future__ import annotations

import argparse
from pathlib import Path

from yingming_core.chat import run_chat
from yingming_core.import_chatgpt import import_chatgpt_export
from yingming_core.memory import MemoryStore
from yingming_core.paths import PROJECT_ROOT
from yingming_core.pet_app import run_pet
from yingming_core.web_server import run_web


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yingming",
        description="樱茗文字版：一个温柔、机灵、会记住你的 AI 伙伴原型。",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("chat", help="启动樱茗文字聊天。")

    remember = subparsers.add_parser("remember", help="从命令行写入一条长期记忆。")
    remember.add_argument("text", help="要让樱茗记住的内容。")
    remember.add_argument("--category", default="manual", help="记忆类别，默认 manual。")

    subparsers.add_parser("show-memory", help="显示当前长期记忆。")

    web = subparsers.add_parser("web", help="启动樱茗 Web 交互界面。")
    web.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1。")
    web.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765。")

    pet = subparsers.add_parser("pet", help="启动樱茗桌面宠物。")
    pet.add_argument("--no-topmost", action="store_true", help="启动时不要置顶窗口。")

    importer = subparsers.add_parser("import-chatgpt", help="导入 ChatGPT 导出的 conversations.json。")
    importer.add_argument("path", help="conversations.json 的路径。")
    importer.add_argument(
        "--limit",
        type=int,
        default=0,
        help="最多读取多少个对话。0 表示不限制。",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command in (None, "chat"):
        run_chat(PROJECT_ROOT)
        return

    if args.command == "remember":
        store = MemoryStore(PROJECT_ROOT / "data" / "memory.json")
        item = store.add(args.text, category=args.category, source="cli")
        print(f"已记住：{item.text}")
        return

    if args.command == "show-memory":
        store = MemoryStore(PROJECT_ROOT / "data" / "memory.json")
        print(store.as_readable_text())
        return

    if args.command == "web":
        run_web(PROJECT_ROOT, host=args.host, port=args.port)
        return

    if args.command == "pet":
        run_pet(PROJECT_ROOT, topmost=not args.no_topmost)
        return

    if args.command == "import-chatgpt":
        limit = None if args.limit == 0 else args.limit
        result = import_chatgpt_export(Path(args.path), PROJECT_ROOT, limit=limit)
        print(f"已提取用户消息：{result.user_message_count} 条")
        print(f"画像草稿：{result.profile_draft_path}")
        print(f"语料文件：{result.corpus_path}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
