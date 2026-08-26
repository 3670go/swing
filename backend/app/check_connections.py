from httpx import HTTPError
from sqlalchemy.exc import SQLAlchemyError
from storage3.exceptions import StorageApiError

from app.config import get_settings
from app.database import Database
from app.storage import SupabaseStorageSigner


def main() -> int:
    """Check configured Postgres and private Storage access without printing secrets."""
    settings = get_settings()
    database = Database(settings)
    storage = SupabaseStorageSigner(settings)
    failures: list[str] = []

    try:
        database.ping()
        print("postgres=ok")
    except SQLAlchemyError as error:
        failures.append(f"postgres={error.__class__.__name__}")
    finally:
        database.close()

    try:
        storage.assert_bucket_access()
        print("storage=ok")
    except (HTTPError, StorageApiError, ValueError) as error:
        failures.append(f"storage={error.__class__.__name__}")

    for failure in failures:
        print(failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
