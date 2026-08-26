import unittest

from app.domain.analysis_status import AnalysisStatusPolicy


class AnalysisStatusPolicyTests(unittest.TestCase):
    def test_completion_transitions_only_from_running(self) -> None:
        transition = AnalysisStatusPolicy.complete("succeeded")

        self.assertEqual(transition.allowed_from, ("running",))
        self.assertEqual(transition.target, "succeeded")

    def test_rejects_non_completion_target(self) -> None:
        with self.assertRaises(ValueError):
            AnalysisStatusPolicy.complete("failed")  # type: ignore[arg-type]

    def test_delete_accepts_every_visible_status(self) -> None:
        transition = AnalysisStatusPolicy.delete()

        self.assertIn("running", transition.allowed_from)
        self.assertIn("failed", transition.allowed_from)
        self.assertNotIn("deleted", transition.allowed_from)
        self.assertEqual(transition.target, "deleted")


if __name__ == "__main__":
    unittest.main()
