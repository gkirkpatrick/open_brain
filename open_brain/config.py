from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "open_brain"
    db_user: str = "superschedules"
    db_password: str = ""

    # AWS Bedrock
    aws_region: str = "us-east-1"
    aws_bedrock_region: str = "us-east-1"
    embedding_model: str = "amazon.titan-embed-text-v2:0"
    embedding_dimensions: int = 1024
    metadata_model: str = "anthropic.claude-3-haiku-20240307-v1:0"

    # Auth
    open_brain_access_key: str = ""

    # Slack (optional)
    slack_signing_secret: str = ""
    slack_bot_token: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def database_url_sync(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


settings = Settings()
