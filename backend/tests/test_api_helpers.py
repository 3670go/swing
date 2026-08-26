import hashlib
import unittest

from fastapi import HTTPException
from pydantic import ValidationError

from app.api import (
    anonymous_session_hash,
    app,
    build_custom_gpt_action_schema,
    classify_media,
    render_coach_reply,
    render_conversation_reply,
    validate_action_download_url,
    verify_action_api_key,
)
from app.schemas import (
    ActionAnalyzeRequest,
    AssessmentFinding,
    BaseAssessment,
    CoachContent,
    CoachReply,
    ConversationReply,
)


def make_coach_reply(conversation: ConversationReply) -> CoachReply:
    assessment_hash = "a" * 64
    return CoachReply(
        base_assessment=BaseAssessment(
            primary_category="arm_body_space",
            importance="medium",
            findings=[
                AssessmentFinding(
                    category="arm_body_space",
                    observation_indexes=[0],
                    summary="손이 오른쪽 골반 옆에 위치합니다.",
                    confidence=0.8,
                )
            ],
            cannot_determine=["Club Path 수치"],
            assessment_hash=assessment_hash,
        ),
        content=CoachContent(
            evidence_mode="video_ready",
            direct_answer="오른힙 이동을 먼저 봐야 해.",
            causal_chain=["골반 전체 이동과 연결됩니다."],
            evidence_boundary="영상 프레임",
            cannot_determine=["압력 수치"],
            observation_indexes=[0],
            base_assessment_hash=assessment_hash,
            single_change="오른힙이 뒤로 도는지만 확인합니다.",
            verification="같은 각도로 다시 촬영합니다.",
        ),
        conversation=conversation,
    )


class ApiHelperTests(unittest.TestCase):
    def test_anonymous_session_hash_never_persists_raw_token(self) -> None:
        token = "browser-session-token-1234"

        result = anonymous_session_hash(token)

        self.assertEqual(result, hashlib.sha256(token.encode("utf-8")).hexdigest())
        self.assertNotIn(token, result)

    def test_text_reply_hides_internal_labels_and_keeps_conversational_close(self) -> None:
        rendered = render_conversation_reply(
            ConversationReply(
                message="가능한 원인을 두 가지로 나눕니다.",
                follow_up_question="잘 맞은 샷에서는 느낌부터 달랐어?",
                question_topic="good_bad_feel",
                invite_mode="compare_good_bad",
            )
        )

        self.assertNotIn("근거 범위", rendered)
        self.assertNotIn("다음 확인", rendered)
        self.assertNotIn("현재 질문에는 영상이 없습니다.", rendered)
        self.assertIn("잘 맞은 샷에서는 느낌부터 달랐어?", rendered)

    def test_text_reply_rejects_mobile_chat_answer_over_limit(self) -> None:
        with self.assertRaises(ValidationError):
            ConversationReply(message="가" * 901)

    def test_media_reply_exposes_conversation_but_not_internal_report_labels(self) -> None:
        rendered = render_coach_reply(
            make_coach_reply(
                ConversationReply(
                    message="오른힙 이동이 먼저 보여.",
                    follow_up_question="잘 맞은 샷에서도 같은 느낌이었어?",
                    question_topic="good_bad_feel",
                    invite_mode="compare_good_bad",
                )
            )
        )

        self.assertIn("오른힙 이동이 먼저 보여.", rendered)
        self.assertIn("잘 맞은 샷에서도 같은 느낌이었어?", rendered)
        self.assertNotIn("OBSERVATION", rendered)
        self.assertNotIn("사용자 FEEL 대조", rendered)

    def test_classifies_photo_and_video_uploads(self) -> None:
        self.assertEqual(classify_media("image/jpeg"), ("photo", ".jpg"))
        self.assertEqual(classify_media("video/quicktime"), ("video", ".mov"))

    def test_rejects_unsupported_upload_type(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            classify_media("application/pdf")

        self.assertEqual(raised.exception.status_code, 415)

    def test_analysis_contract_accepts_multiple_files(self) -> None:
        request_body = app.openapi()["paths"]["/v1/analyze"]["post"]["requestBody"]
        schema_reference = request_body["content"]["multipart/form-data"]["schema"]["$ref"]
        schema_name = schema_reference.rsplit("/", 1)[-1]
        files_schema = app.openapi()["components"]["schemas"][schema_name]["properties"]["files"]

        self.assertEqual(files_schema["type"], "array")
        self.assertEqual(files_schema["items"]["contentMediaType"], "application/octet-stream")

    def test_custom_gpt_schema_uses_required_file_reference_parameter(self) -> None:
        schema = build_custom_gpt_action_schema("https://api.example.com/")
        operation = schema["paths"]["/v1/actions/analyze"]["post"]
        request_schema = operation["requestBody"]["content"]["application/json"]["schema"]

        self.assertEqual(schema["servers"], [{"url": "https://api.example.com"}])
        self.assertIn("openaiFileIdRefs", request_schema["required"])
        self.assertEqual(
            request_schema["properties"]["openaiFileIdRefs"]["items"],
            {"type": "string"},
        )

    def test_action_request_accepts_runtime_file_reference_objects(self) -> None:
        request = ActionAnalyzeRequest.model_validate(
            {
                "session_id": "custom-gpt-session-1234",
                "openaiFileIdRefs": [
                    {
                        "name": "swing.mp4",
                        "id": "file-example",
                        "mime_type": "video/mp4",
                        "download_link": (
                            "https://files.oaiusercontent.com/file-example?signature=test"
                        ),
                    }
                ],
                "context": {
                    "shot_profile": "full_swing",
                    "club": "7번 아이언",
                    "camera_view": "down_the_line",
                    "handedness": "right",
                    "analysis_goal": "posture_correction",
                },
            }
        )

        self.assertEqual(request.openai_file_id_refs[0].mime_type, "video/mp4")

    def test_action_download_rejects_non_openai_or_non_https_urls(self) -> None:
        with self.assertRaises(HTTPException) as non_https:
            validate_action_download_url(
                "http://files.oaiusercontent.com/file.mp4",
                ("files.oaiusercontent.com",),
            )
        with self.assertRaises(HTTPException) as wrong_host:
            validate_action_download_url(
                "https://example.com/file.mp4",
                ("files.oaiusercontent.com",),
            )

        self.assertEqual(non_https.exception.detail, "ACTION_FILE_URL_UNTRUSTED")
        self.assertEqual(wrong_host.exception.detail, "ACTION_FILE_URL_UNTRUSTED")

    def test_action_bearer_token_requires_exact_match(self) -> None:
        verify_action_api_key("Bearer correct-secret", "correct-secret")

        with self.assertRaises(HTTPException) as raised:
            verify_action_api_key("Bearer wrong-secret", "correct-secret")

        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
