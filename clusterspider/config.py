from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    model_config = {"env_prefix": "CS_", "env_file": ".env", "extra": "ignore"}

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"
    neo4j_max_pool_size: int = 50

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # API Keys (third-party data sources)
    hibp_api_key: str = ""
    github_token: str = ""
    ipinfo_token: str = ""

    # Rate Limits (requests per second)
    hibp_rate_limit: float = 0.67
    github_rate_limit: float = 0.5
    crtsh_rate_limit: float = 2.0
    ipinfo_rate_limit: float = 5.0

    # Freshness (hours before re-collection is allowed)
    freshness_window_hours: int = 24

    # Graph query limits
    max_graph_depth: int = 5
    default_graph_depth: int = 2
    max_results_per_page: int = 100

    # Encryption key for stored API keys
    fernet_key: str = ""

    # Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    # SQLite (legacy + freshness tracking)
    sqlite_path: str = "clusterspider.db"


settings = Settings()
