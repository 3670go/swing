"""로컬 체험용 HTTP 서버.

표준 라이브러리만 쓴다. 외부 LLM·DB·Supabase 를 연결하지 않고 서버에 아무것도 저장하지 않는다.
대화 상태는 브라우저의 localStorage 에만 남는다.

    python web_app.py --host 127.0.0.1 --port 8765
"""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pydantic import ValidationError

from demo_renderer import render_demo_reply
from schemas import ConversationInput, InputIntegrityError, TrackerError
from state_tracker import track

WEB_ROOT = Path(__file__).resolve().parent / "web"
MAX_BODY_BYTES = 2_000_000

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


class TrackerRequestHandler(BaseHTTPRequestHandler):
    server_version = "ConversationStateTrackerPOC/0.2"
    quiet = False

    # -- helpers ---------------------------------------------------------

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _send_error_json(self, status: HTTPStatus, code: str, message: str, detail=None) -> None:
        """구조화 오류만 돌려준다. 부분 상태는 절대 포함하지 않는다."""
        payload: dict = {"error": {"code": code, "message": message}}
        if detail is not None:
            payload["error"]["detail"] = detail
        self._send_json(status, payload)

    def log_message(self, fmt: str, *args) -> None:  # noqa: A002
        if not self.quiet:
            super().log_message(fmt, *args)

    # -- routes ----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        entry = STATIC_FILES.get(path)
        if entry is None:
            self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", f"경로가 없습니다: {path}")
            return
        filename, content_type = entry
        target = WEB_ROOT / filename
        if not target.is_file():
            self._send_error_json(
                HTTPStatus.NOT_FOUND, "not_found", f"정적 파일이 없습니다: {filename}"
            )
            return
        self._send(HTTPStatus.OK, target.read_bytes(), content_type)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/api/track":
            self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", f"경로가 없습니다: {path}")
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_error_json(
                HTTPStatus.BAD_REQUEST, "bad_content_length", "Content-Length 가 올바르지 않습니다"
            )
            return
        if length <= 0:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "empty_body", "요청 본문이 비어 있습니다")
            return
        if length > MAX_BODY_BYTES:
            self._send_error_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body_too_large", "요청 본문이 너무 큽니다"
            )
            return

        body = self.rfile.read(length)
        try:
            raw = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            self._send_error_json(
                HTTPStatus.BAD_REQUEST, "invalid_json", f"JSON 을 읽을 수 없습니다: {error}"
            )
            return

        try:
            payload = ConversationInput.model_validate(raw)
        except ValidationError as error:
            self._send_error_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "validation_error",
                "입력 스키마를 만족하지 않습니다",
                detail=json.loads(error.json()),
            )
            return

        try:
            state = track(payload)
        except InputIntegrityError as error:
            self._send_error_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "input_integrity_error",
                str(error),
                detail={"type": type(error).__name__},
            )
            return
        except TrackerError as error:
            self._send_error_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "tracker_error",
                str(error),
                detail={"type": type(error).__name__},
            )
            return

        self._send_json(
            HTTPStatus.OK,
            {
                "conversation_state": state.model_dump(mode="json"),
                "demo_reply": render_demo_reply(state),
            },
        )


def create_server(host: str = "127.0.0.1", port: int = 8765, *, quiet: bool = False):
    """서버 객체만 만든다. 실제 serve 는 호출자가 한다."""
    handler = type("BoundHandler", (TrackerRequestHandler,), {"quiet": quiet})
    return ThreadingHTTPServer((host, port), handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Conversation state tracker POC web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    server = create_server(args.host, args.port, quiet=args.quiet)
    print(f"conversation-state-tracker POC: http://{args.host}:{args.port}")
    print("Ctrl+C 로 종료합니다. 서버에는 아무것도 저장하지 않습니다.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
