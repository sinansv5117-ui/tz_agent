import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:YourNewPassword@127.0.0.1:1234/bus_database",
    )
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    groq_base_url: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    temperature: float = float(os.getenv("TEMPERATURE", "0.4"))
    max_tokens: int = int(os.getenv("MAX_TOKENS", "300"))
    max_route_hops: int = int(os.getenv("MAX_ROUTE_HOPS", "4"))
    max_route_results: int = int(os.getenv("MAX_ROUTE_RESULTS", "50"))


settings = Settings()
