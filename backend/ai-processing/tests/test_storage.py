import unittest

from app.storage import _read_upload_token, build_resumable_endpoint


class SignedResponse:
    token = "temporary-token"


class StorageHelpersTests(unittest.TestCase):
    def test_uses_direct_storage_hostname_for_supabase_cloud(self) -> None:
        endpoint = build_resumable_endpoint("https://project-ref.supabase.co")

        self.assertEqual(
            endpoint,
            "https://project-ref.storage.supabase.co/storage/v1/upload/resumable",
        )

    def test_uses_project_storage_path_for_local_supabase(self) -> None:
        endpoint = build_resumable_endpoint("http://localhost:54321")

        self.assertEqual(endpoint, "http://localhost:54321/storage/v1/upload/resumable")

    def test_reads_typed_supabase_response_token(self) -> None:
        self.assertEqual(_read_upload_token(SignedResponse()), "temporary-token")

    def test_rejects_missing_token(self) -> None:
        with self.assertRaises(ValueError):
            _read_upload_token({"path": "video.mp4"})


if __name__ == "__main__":
    unittest.main()
