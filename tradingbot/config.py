from pathlib import Path
import typing

import toml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, TomlConfigSettingsSource


class Config(BaseSettings):
    _instance: typing.ClassVar["Config"] = None
    
    class _GeneralConfig(BaseModel):
        db_url: str = Field(default=f"sqlite:///{Path(__file__).parent / 'tradingbot.db'}")
        strategy_dir: str = Field(default=Path(__file__).parent / 'strategy')
        log_dir: str = Field(default=Path(__file__).parent / 'logs')
        http_proxy: str | None = Field(default=None)
        https_proxy: str | None = Field(default=None)
        cluster_url: str | None = Field(default=None)

    class _SourceConfig(BaseModel):
        model_config = ConfigDict(extra="allow")

        class _BinanceSourceConfig(BaseModel):
            api_key: str | None = Field(default=None)
            api_secret: str | None = Field(default=None)

        binance: _BinanceSourceConfig | None = Field(default=None)

    class _ExchangeConfig(BaseModel):
        model_config = ConfigDict(extra="allow")

        class _CCXTExchangeConfig(BaseModel):
            model_config = ConfigDict(extra="allow")

            name: str

        ccxt: _CCXTExchangeConfig | None = Field(default=None)

    class _NotificationConfig(BaseModel):
        model_config = ConfigDict(extra="allow")

        class _SlackConfig(BaseModel):
            bot_token: str
            channel: str

        slack: _SlackConfig | None = Field(default=None)

    class _LoggingConfig(BaseModel):
        version: int = 1
        disable_existing_loggers: bool = False

        formatters: dict[str, dict[str, typing.Any]]
        handlers: dict[str, dict[str, typing.Any]]
        loggers: dict[str, dict[str, typing.Any]]
        root: dict[str, typing.Any]

    general: _GeneralConfig
    source: _SourceConfig
    exchange: _ExchangeConfig
    notification: _NotificationConfig
    logging: _LoggingConfig

    model_config = SettingsConfigDict(
        toml_file=Path(__file__).parent / "config.toml", env_prefix="TB_", env_nested_delimiter="_", validate_assignment=True
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: typing.Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        
        search_path = [
            Path.cwd() / "config.toml",  # current directory
            Path.cwd().parent / "config.toml",  # parent directory
        ]
        toml_file = cls.model_config.get("toml_file")  # default
        for path in search_path:
            if path.exists():
                toml_file = path
                print(f"Loading config.toml from '{toml_file}'")
                break

        return (env_settings, dotenv_settings, TomlConfigSettingsSource(settings_cls, toml_file))

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance.__init__(*args, **kwargs)  # Initialize once
        return cls._instance

    def save(self):
        """Save the current state of the configuration to the TOML file."""
        toml_file = self.model_config.get("toml_file")
        if toml_file:
            with open(toml_file, "w") as f:
                toml.dump(self.model_dump(), f)
