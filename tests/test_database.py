from backend.database import DEFAULT_DATABASE_URL, database_url
from backend.store import DatabaseStore


def test_database_url_comes_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("PIANO_DATABASE_URL", "sqlite+pysqlite:///configured.db")
    assert database_url() == "sqlite+pysqlite:///configured.db"

    monkeypatch.delenv("PIANO_DATABASE_URL")
    assert database_url() == DEFAULT_DATABASE_URL


def test_store_data_persists_across_store_instances(tmp_path) -> None:
    url = f"sqlite+pysqlite:///{tmp_path / 'persistent.db'}"
    first = DatabaseStore(url)
    created = first.create_student("Persistent Student", 4, "16:15")
    first.engine.dispose()

    second = DatabaseStore(url)
    assert second.student_for_token(created.token).name == "Persistent Student"
    second.engine.dispose()
