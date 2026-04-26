"""
Configuration management module for the Insight Engine.
Handles environment variables and .env parameters.
"""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    INSIGHT_ENGINE_API_KEY: Optional[str] = Field("2ef1efed81bc46da842bbf3c25713233.JmKaCGaSK580dbpA", description="Insight Engine LLM API key")
    INSIGHT_ENGINE_BASE_URL: Optional[str] = Field(None, description="Insight Engine LLM base url")
    INSIGHT_ENGINE_MODEL_NAME: Optional[str] = Field(None, description="Insight Engine LLM model name")
    INSIGHT_ENGINE_PROVIDER: Optional[str] = Field(None, description="Insight Engine provider")

    DB_HOST: Optional[str] = Field("localhost", description="Database host")
    DB_USER: Optional[str] = Field("root", description="Database username")
    DB_PASSWORD: Optional[str] = Field("root", description="Database password")
    DB_NAME: Optional[str] = Field("FSA", description="Database name")
    DB_PORT: int = Field(3306, description="Database port")
    DB_CHARSET: str = Field("utf8mb4", description="Database charset")
    DB_DIALECT: Optional[str] = Field("mysql", description="Database dialect")

    MAX_REFLECTIONS: int = Field(3, description="Max reflection rounds")
    MAX_PARAGRAPHS: int = Field(6, description="Max paragraphs")
    SEARCH_TIMEOUT: int = Field(240, description="Search timeout")
    MAX_CONTENT_LENGTH: int = Field(500000, description="Max content length")

    DEFAULT_SEARCH_HOT_CONTENT_LIMIT: int = Field(100, description="Default hot-content limit")
    DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE: int = Field(50, description="Default global topic limit per table")
    DEFAULT_SEARCH_TOPIC_BY_DATE_LIMIT_PER_TABLE: int = Field(100, description="Default topic-by-date limit per table")
    DEFAULT_GET_COMMENTS_FOR_TOPIC_LIMIT: int = Field(500, description="Default comments limit")
    DEFAULT_SEARCH_TOPIC_ON_PLATFORM_LIMIT: int = Field(200, description="Default platform topic limit")
    MAX_SEARCH_RESULTS_FOR_LLM: int = Field(0, description="Max search results passed to LLM")
    MAX_HIGH_CONFIDENCE_SENTIMENT_RESULTS: int = Field(0, description="Max high-confidence sentiment results")

    OUTPUT_DIR: str = Field("reports", description="Output directory")
    SAVE_INTERMEDIATE_STATES: bool = Field(True, description="Save intermediate states")

    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False
        extra = "allow"


settings = Settings()
