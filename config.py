from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: Optional[str] = None
    LLM_MODEL: str = "gpt-4o-mini"
    
    DB_PATH: str = str(BASE_DIR / "database" / "schedule.db")
    MCP_SERVER_SCRIPT: str = str(BASE_DIR / "mcp_server" / "server.py")
    
    # Режим отладки (логирование всех tool calls в консоль)
    DEBUG_TOOL_CALLS: bool = True
    
    # Интервал проверки напоминаний в секундах
    REMINDER_CHECK_INTERVAL_SECONDS: int = 30

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
