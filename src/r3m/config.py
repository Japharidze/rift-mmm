import os
from pathlib import Path

from psycopg.conninfo import make_conninfo
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = ROOT / "migrations"
DATA_DIR = ROOT / "data"
ANCHORS_FILE = ROOT / "anchors" / "champions.yaml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ROOT / ".env"), extra="ignore"
    )

    # Local development supplies these five. A managed host (Railway, Fly,
    # Heroku) supplies one DATABASE_URL instead and does not let you pick, so
    # both are accepted and the URL wins when present.
    postgres_user: str = ""
    postgres_password: str = ""
    postgres_db: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str = ""

    # Empty by default: migrate and ingest must keep working without a Riot
    # key. riot_api.py raises when it is actually needed and missing.
    riot_api_key: str = ""

    # Same reasoning: everything but labelling must keep working without it.
    # r3m.labeling.run raises when it is actually needed and missing.
    anthropic_api_key: str = ""

    @property
    def db_url(self) -> str:
        if not self.database_url and not self.postgres_db:
            # Said plainly, because the alternative is a connection timeout
            # against localhost inside a container, which reads as a network
            # problem and is a configuration one. A managed host that offers to
            # import POSTGRES_* from .env.example makes this easy to hit: those
            # are development values, and accepting them gives a host of
            # "localhost" that means nothing in a container.
            raise RuntimeError(
                "no database configured: set DATABASE_URL (a managed host "
                "supplies one), or POSTGRES_DB and friends for a local "
                "database. See docs/deploy.md."
            )
        if self.database_url:
            # psycopg wants postgresql://; some hosts still emit postgres://
            return self.database_url.replace("postgres://", "postgresql://", 1)
        return make_conninfo(
            host=self.postgres_host,
            dbname=self.postgres_db,
            user=self.postgres_user,
            password=self.postgres_password,
            port=self.postgres_port,
        )

settings = Settings()  # type: ignore[call-arg]
