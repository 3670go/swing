"""로컬 체험 POC 의 HTTP 계약 테스트.

127.0.0.1 의 임시 포트에 서버를 띄우고 표준 라이브러리 클라이언트로만 검증한다.
테스트가 끝나면 서버를 반드시 종료한다.
"""

from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app import create_server  # noqa: E402

FIXTURES = ROOT / "fixtures"
IRON_TOPIC = {
    "topic_id": "t2",
    "user_problem": "아이언에서 뒤땅이 난다",
    "root_problem": "체중이 오른발에 남는다",
}


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class WebAppTestCase(unittest.TestCase):
    server = None
    thread = None
    base = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server("127.0.0.1", 0, quiet=True)
        host, port = cls.server.server_address[:2]
        cls.base = f"http://{host}:{port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()

    def get(self, path: str):
        try:
            with urllib.request.urlopen(f"{self.base}{path}", timeout=10) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def post(self, path: str, body: bytes, content_type: str = "application/json"):
        request = urllib.request.Request(
            f"{self.base}{path}", data=body, headers={"Content-Type": content_type}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def post_payload(self, payload: dict):
        return self.post("/api/track", json.dumps(payload, ensure_ascii=False).encode("utf-8"))


class StaticRoutes(WebAppTestCase):
    def test_health(self) -> None:
        status, body = self.get("/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"status": "ok"})

    def test_index(self) -> None:
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"<title>Conversation State Tracker POC</title>", body)

    def test_assets(self) -> None:
        for path in ("/app.js", "/style.css"):
            with self.subTest(path=path):
                status, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertGreater(len(body), 0)

    def test_unknown_path(self) -> None:
        status, _ = self.get("/definitely-not-here")
        self.assertEqual(status, 404)


class TrackEndpoint(WebAppTestCase):
    def test_valid_payload_returns_state_and_reply(self) -> None:
        status, data = self.post_payload(fixture("06_practice_result_improved.json"))
        self.assertEqual(status, 200)
        self.assertIn("conversation_state", data)
        self.assertIn("demo_reply", data)
        state = data["conversation_state"]
        self.assertEqual(state["progress"]["level"], "USER_REPORTED_PROGRESS")
        self.assertFalse(state["progress"]["swing_improvement_confirmed"])
        self.assertTrue(data["demo_reply"].strip())

    def test_video_verified_is_distinguished_over_http(self) -> None:
        _, reported = self.post_payload(fixture("06_practice_result_improved.json"))
        _, verified = self.post_payload(fixture("06b_video_verified_progress.json"))
        self.assertFalse(reported["conversation_state"]["progress"]["swing_improvement_confirmed"])
        self.assertTrue(verified["conversation_state"]["progress"]["swing_improvement_confirmed"])
        self.assertNotEqual(reported["demo_reply"], verified["demo_reply"])

    def test_malformed_json_is_400(self) -> None:
        status, data = self.post("/api/track", b"{not json")
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "invalid_json")
        self.assertNotIn("conversation_state", data)

    def test_empty_body_is_400(self) -> None:
        status, data = self.post("/api/track", b"")
        self.assertEqual(status, 400)
        self.assertNotIn("conversation_state", data)

    def test_schema_violation_is_422_without_partial_state(self) -> None:
        payload = fixture("06_practice_result_improved.json")
        del payload["messages"]
        status, data = self.post_payload(payload)
        self.assertEqual(status, 422)
        self.assertEqual(data["error"]["code"], "validation_error")
        self.assertNotIn("conversation_state", data)
        self.assertNotIn("demo_reply", data)

    def test_integrity_violation_is_422_without_partial_state(self) -> None:
        payload = fixture("06_practice_result_improved.json")
        payload["behavior_events"][0]["related_message_id"] = "does-not-exist"
        status, data = self.post_payload(payload)
        self.assertEqual(status, 422)
        self.assertEqual(data["error"]["code"], "input_integrity_error")
        self.assertEqual(data["error"]["detail"]["type"], "DanglingReferenceError")
        self.assertNotIn("conversation_state", data)

    def test_unknown_post_path_is_404(self) -> None:
        status, _ = self.post("/api/nope", b"{}")
        self.assertEqual(status, 404)


class TopicSwitchingOverHttp(WebAppTestCase):
    def test_switching_topic_changes_selected_context(self) -> None:
        payload = fixture("11_mixed_topics.json")
        topics = {m["message_id"]: m["topic_id"] for m in payload["messages"]}
        current = [m for m in payload["messages"] if m["role"] == "user"][-1]["message_id"]

        status_a, driver = self.post_payload(payload)
        switched = deepcopy(payload)
        switched["active_coaching_topic"] = IRON_TOPIC
        status_b, iron = self.post_payload(switched)

        self.assertEqual((status_a, status_b), (200, 200))
        driver_ids = driver["conversation_state"]["selected_context_message_ids"]
        iron_ids = iron["conversation_state"]["selected_context_message_ids"]
        self.assertNotEqual(driver_ids, iron_ids)
        for message_id in driver_ids:
            if message_id != current:
                self.assertEqual(topics[message_id], "t1")
        for message_id in iron_ids:
            if message_id != current:
                self.assertEqual(topics[message_id], "t2")


if __name__ == "__main__":
    unittest.main()
