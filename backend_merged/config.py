from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "University ERP API"
    DATABASE_URL: str = "sqlite:///./erp.db"
    SECRET_KEY: str = "change-this-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Email settings (leave empty to print emails in the terminal instead)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    # Escalation settings
    ESCALATION_HOURS: int = 24

    # False = send emails directly (no Redis needed). True = use Celery + Redis.
    USE_CELERY: bool = False

    class Config:
        env_file = ".env"


settings = Settings()