import unittest

from app.database import alembic_database_url, normalize_database_url


class NormalizeDatabaseUrlTests(unittest.TestCase):
    def test_normalizes_standard_postgresql_url(self) -> None:
        result = normalize_database_url("postgresql://user:secret@host:6543/postgres")

        self.assertEqual(
            result,
            "postgresql+psycopg://user:secret@host:6543/postgres",
        )

    def test_preserves_psycopg_dialect_url(self) -> None:
        url = "postgresql+psycopg://user:secret@host:6543/postgres"

        self.assertEqual(normalize_database_url(url), url)

    def test_rejects_non_postgresql_url(self) -> None:
        with self.assertRaises(ValueError):
            normalize_database_url("sqlite:///local.db")

    def test_escapes_percent_encoded_password_for_alembic(self) -> None:
        result = alembic_database_url("postgresql://user:secret%21@host:6543/postgres")

        self.assertEqual(
            result,
            "postgresql+psycopg://user:secret%%21@host:6543/postgres",
        )


if __name__ == "__main__":
    unittest.main()
