import os
from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator


DATABASE_URL_ENV = "PIANO_DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite+pysqlite:///./piano.db"


def database_url() -> str:
    return os.getenv(DATABASE_URL_ENV, DEFAULT_DATABASE_URL)


class UtcDateTime(TypeDecorator[datetime]):
    """Persist aware datetimes in UTC and restore awareness on every dialect."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, _dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Naive datetimes cannot be stored")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, _dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


CONSTRAINT_NAMES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONSTRAINT_NAMES)


def create_database_engine(url: str | None = None) -> Engine:
    resolved_url = url or database_url()
    options: dict[str, object] = {"pool_pre_ping": True}
    if resolved_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if resolved_url.endswith(":memory:"):
            options["poolclass"] = StaticPool
    return create_engine(resolved_url, **options)


def create_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
