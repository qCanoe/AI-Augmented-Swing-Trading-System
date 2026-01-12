"""配置加载模块 - 从环境变量和 .env 文件加载配置。"""

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RunMode(str, Enum):
    """运行模式枚举。"""

    PAPER = "paper"  # 纸交易
    LIVE = "live"  # 实盘


class LogFormat(str, Enum):
    """日志格式枚举。"""

    JSON = "json"
    CONSOLE = "console"


class Settings(BaseSettings):
    """系统配置设置。

    从环境变量和 .env 文件加载配置。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==================== 运行模式 ====================
    mode: RunMode = Field(default=RunMode.PAPER, description="运行模式: paper 或 live")

    # ==================== Binance API ====================
    binance_api_key: str = Field(default="", description="Binance API Key")
    binance_api_secret: str = Field(default="", description="Binance API Secret")
    binance_testnet: bool = Field(default=True, description="是否使用 Binance 测试网")

    # ==================== OpenRouter API ====================
    openrouter_api_key: str = Field(default="", description="OpenRouter API Key")
    openrouter_model: str = Field(
        default="anthropic/claude-3.5-sonnet",
        description="OpenRouter 模型名称",
    )
    openrouter_timeout: int = Field(default=30, description="LLM 调用超时（秒）")

    # ==================== 风控参数 ====================
    risk_per_trade_pct: float = Field(
        default=0.5,
        ge=0.1,
        le=2.0,
        description="单笔最大风险（账户净值百分比）",
    )
    stop_loss_atr_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        le=5.0,
        description="止损 ATR 倍数",
    )
    max_holding_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="时间止损（天）",
    )
    max_consecutive_losses: int = Field(
        default=3,
        ge=1,
        le=10,
        description="连续亏损停机阈值",
    )
    max_weekly_drawdown_pct: float = Field(
        default=3.0,
        ge=1.0,
        le=10.0,
        description="周最大回撤停机阈值（百分比）",
    )
    max_total_exposure_pct: float = Field(
        default=10.0,
        ge=1.0,
        le=50.0,
        description="总敞口限制（账户净值百分比）",
    )

    # ==================== 策略参数 ====================
    pullback_atr_threshold: float = Field(
        default=0.5,
        ge=0.1,
        le=2.0,
        description="回踩阈值（ATR 倍数）",
    )
    atr_high_quantile: float = Field(
        default=0.8,
        ge=0.5,
        le=0.99,
        description="ATR 高波动分位阈值",
    )

    # ==================== 日志配置 ====================
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="日志级别",
    )
    log_format: LogFormat = Field(
        default=LogFormat.CONSOLE,
        description="日志输出格式",
    )

    # ==================== 数据存储 ====================
    journal_dir: Path = Field(
        default=Path("data/journal"),
        description="交易日志存储目录",
    )

    @field_validator("journal_dir", mode="before")
    @classmethod
    def parse_journal_dir(cls, v: str | Path) -> Path:
        """将字符串转换为 Path 对象。"""
        return Path(v) if isinstance(v, str) else v

    def ensure_directories(self) -> None:
        """确保必要的目录存在。"""
        self.journal_dir.mkdir(parents=True, exist_ok=True)

    @property
    def is_paper_mode(self) -> bool:
        """是否为纸交易模式。"""
        return self.mode == RunMode.PAPER

    @property
    def is_live_mode(self) -> bool:
        """是否为实盘模式。"""
        return self.mode == RunMode.LIVE

    def validate_for_live(self) -> list[str]:
        """验证实盘模式的必要配置，返回缺失项列表。"""
        missing = []
        if not self.binance_api_key:
            missing.append("BINANCE_API_KEY")
        if not self.binance_api_secret:
            missing.append("BINANCE_API_SECRET")
        if not self.openrouter_api_key:
            missing.append("OPENROUTER_API_KEY")
        return missing


# 全局配置实例（延迟初始化）
_settings: Settings | None = None


def get_settings() -> Settings:
    """获取全局配置实例。"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """重新加载配置。"""
    global _settings
    _settings = Settings()
    return _settings
