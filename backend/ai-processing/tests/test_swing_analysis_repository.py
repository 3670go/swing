import unittest
import uuid
from typing import Any

from app.domain.models import ShotContext
from app.repositories.swing_analyses import SwingAnalysisRepository


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, value: Any) -> None:
        self.added.append(value)

    def flush(self) -> None:
        return None


class SwingAnalysisRepositoryTests(unittest.TestCase):
    def test_question_is_not_duplicated_into_user_feel(self) -> None:
        session = FakeSession()
        repository = SwingAnalysisRepository()

        swing_session = repository.create_swing_session(
            session,  # type: ignore[arg-type]
            owner_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            context=ShotContext(
                shot_profile="full_swing",
                club="7번 아이언",
                camera_view="down_the_line",
                handedness="right",
                analysis_goal="posture_correction",
            ),
            question="자꾸 땡겨치는 느낌이야",
        )

        self.assertEqual(swing_session.user_question, "자꾸 땡겨치는 느낌이야")
        self.assertIsNone(swing_session.user_feel)


if __name__ == "__main__":
    unittest.main()
