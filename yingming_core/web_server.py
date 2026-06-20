from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

from yingming_core.import_chatgpt import import_chatgpt_conversations
from yingming_core.service import YingmingService


class YingmingWebServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], project_root: Path):
        super().__init__(server_address, YingmingRequestHandler)
        self.project_root = project_root
        self.web_root = project_root / "web"
        self.service = YingmingService(project_root)


class YingmingRequestHandler(BaseHTTPRequestHandler):
    server: YingmingWebServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self.send_json(self.server.service.state())
            return

        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/chat":
                body = self.read_json()
                self.send_json(self.server.service.reply(str(body.get("message", ""))))
                return

            if parsed.path == "/api/memory":
                body = self.read_json()
                self.send_json(
                    self.server.service.remember(
                        str(body.get("text", "")),
                        category=str(body.get("category", "manual")),
                    )
                )
                return

            if parsed.path == "/api/profile":
                body = self.read_json()
                self.send_json(self.server.service.save_profile(str(body.get("profile", ""))))
                return

            if parsed.path == "/api/history/clear":
                self.send_json(self.server.service.clear_history())
                return

            if parsed.path == "/api/import-chatgpt":
                body = self.read_json(max_bytes=80 * 1024 * 1024)
                conversations = body.get("conversations")
                if not isinstance(conversations, list):
                    raise ValueError("上传内容不是 ChatGPT conversations.json 的列表格式。")
                result = import_chatgpt_conversations(conversations, self.server.project_root)
                draft = result.profile_draft_path.read_text(encoding="utf-8")
                self.send_json(
                    {
                        "user_message_count": result.user_message_count,
                        "profile_draft": draft,
                        "profile_draft_path": str(result.profile_draft_path),
                        "corpus_path": str(result.corpus_path),
                    }
                )
                return

            self.send_error_json(HTTPStatus.NOT_FOUND, "没有这个 API。")
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # noqa: BLE001 - keep local prototype errors visible.
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def serve_static(self, request_path: str) -> None:
        web_root = self.server.web_root.resolve()
        relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        static_path = (web_root / relative).resolve()

        try:
            static_path.relative_to(web_root)
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if not static_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(static_path.name)[0] or "application/octet-stream"
        data = static_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_json(self, max_bytes: int = 2 * 1024 * 1024) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > max_bytes:
            raise ValueError("请求内容太大。")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象。")
        return data

    def send_json(self, data: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status=status)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_web(project_root: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = YingmingWebServer((host, port), project_root)
    actual_host, actual_port = server.server_address
    safe_print(f"樱茗 Web 已启动：http://{actual_host}:{actual_port}")
    safe_print("按 Ctrl+C 结束。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        safe_print("\n樱茗 Web 已关闭。")
    finally:
        server.server_close()


def safe_print(text: str) -> None:
    if sys.stdout is not None:
        print(text)
