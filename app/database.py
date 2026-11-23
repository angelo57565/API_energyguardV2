import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings
from .dburl import normalize_database_url

settings = get_settings()
DATABASE_URL, _ssl_from_url = normalize_database_url(settings.database_url)


def _connect_args() -> dict:
    if DATABASE_URL.startswith("sqlite"):
        return {"check_same_thread": False}
    ca = settings.database_ssl_ca
    if settings.database_ssl_ca_pem:
        path = Path(tempfile.gettempdir()) / "energyguard-db-ca.pem"
        path.write_text(settings.database_ssl_ca_pem.replace("\\n", "\n"))
        ca = str(path)
    if ca:
        return {"ssl": {"ca": ca}}  # criptografa e confere o certificado do servidor
    if settings.database_ssl or _ssl_from_url:
        return {"ssl": {"check_hostname": False}}  # criptografa, sem conferir o certificado
    return {}


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args=_connect_args(),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate() -> None:
    """Aplica as revisões pendentes ao banco configurado."""
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
