from datetime import timedelta

from sqlalchemy import select

from backend.database import DEFAULT_DATABASE_URL, database_url
from backend.db_models import LessonRecord
from backend.models import LessonStatus
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


def test_legacy_seed_schedule_gap_is_repaired(tmp_path) -> None:
    url = f"sqlite+pysqlite:///{tmp_path / 'legacy-seed.db'}"
    first = DatabaseStore(url)
    with first._sessions.begin() as session:
        scheduled = session.scalars(
            select(LessonRecord)
            .where(LessonRecord.status == LessonStatus.SCHEDULED.value)
            .order_by(LessonRecord.starts_at.desc())
        ).all()
        for lesson in scheduled:
            lesson.starts_at += timedelta(days=7)
            session.flush([lesson])
    first.engine.dispose()

    second = DatabaseStore(url)
    anna = second.student_for_token("anna")
    history = second.lesson_history(anna.id)
    done = [lesson for lesson in history if lesson.status == LessonStatus.DONE][-1]
    scheduled = [lesson for lesson in history if lesson.status == LessonStatus.SCHEDULED][0]

    assert scheduled.starts_at - done.starts_at == timedelta(days=7)
    second.engine.dispose()
