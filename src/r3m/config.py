import os
from pathlib import Path

from psycopg.conninfo import make_conninfo
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = ROOT / "migrations"
DATA_DIR = ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ROOT / ".env"), extra="ignore"
    )

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Empty by default: migrate and ingest must keep working without a Riot
    # key. riot_api.py raises when it is actually needed and missing.
    riot_api_key: str = ""

    # Same reasoning: everything but labelling must keep working without it.
    # r3m.labeling.run raises when it is actually needed and missing.
    anthropic_api_key: str = ""

    @property
    def db_url(self) -> str:
        return make_conninfo(
            host=self.postgres_host,
            dbname=self.postgres_db,
            user=self.postgres_user,
            password=self.postgres_password,
            port=self.postgres_port,
        )

settings = Settings()  # type: ignore[call-arg]
