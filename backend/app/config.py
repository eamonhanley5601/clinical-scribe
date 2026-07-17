import json
import os
from functools import lru_cache

import boto3
from pydantic_settings import BaseSettings


def _load_from_secrets_manager(secret_id: str) -> dict:
    client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    response = client.get_secret_value(SecretId=secret_id)
    return json.loads(response["SecretString"])


class Settings(BaseSettings):
    environment: str = "local"
    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    openrouter_api_key: str
    # OpenRouter is provider-agnostic (OpenAI-compatible API), so swapping to a paid frontier
    # model in production is a one-line config change -- no code change needed. The free-tier
    # default keeps this take-home at zero marginal cost.
    llm_model: str = "openai/gpt-oss-20b:free"
    cors_origins: list[str] = ["http://localhost:5173"]

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    """
    In production (environment=aws), secrets come from AWS Secrets Manager rather than
    plaintext env vars or a committed .env file. AWS_SECRET_ID names the secret; its JSON
    body supplies database_url / jwt_secret / openrouter_api_key at process start.
    """
    if os.environ.get("APP_ENV") == "aws":
        secret_id = os.environ["AWS_SECRET_ID"]
        secret = _load_from_secrets_manager(secret_id)
        return Settings(environment="aws", **secret)
    return Settings()
