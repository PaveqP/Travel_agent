import os
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: str
    token: SecretStr
    base_url: str
    database_url: SecretStr | None = None
    api_token: SecretStr | None = None
    deadline: int = Field(default=90, ge=5, le=180)


def environment() -> dict[str, str]:
    values = {k: v for k, v in {**dotenv_values('.env'), **os.environ}.items() if v is not None}
    if not values.get('TAVILY_API_KEY') and values.get('TAVILY'):
        values['TAVILY_API_KEY'] = values['TAVILY']
    return values


def settings(env: dict[str, str]) -> Settings:
    return Settings(model=env['MODEL'], token=env['TOKEN'], base_url=env['BASE_URL'],
                    database_url=env.get('TRAVEL_DATABASE_URL'), api_token=env.get('TRAVEL_API_TOKEN'))
