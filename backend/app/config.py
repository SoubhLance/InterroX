from pathlib import Path
from typing import List, Union
import json
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory pointing to backend/
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    ENV: str = "dev"
    REDIS_URL: str = "redis://localhost:6379/0"
    CORS_ORIGINS: Union[List[str], str] = "http://localhost:5173"
    SESSION_TTL_SECONDS: int = 7200
    TESSERACT_CMD: str = ""

    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        if isinstance(self.CORS_ORIGINS, str):
            val = self.CORS_ORIGINS.strip()
            if val.startswith("[") and val.endswith("]"):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed]
                except Exception:
                    pass
            return [origin.strip() for origin in val.split(",") if origin.strip()]
        return ["http://localhost:5173"]


settings = Settings()
