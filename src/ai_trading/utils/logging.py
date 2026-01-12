"""结构化日志配置模块。

使用 structlog 提供结构化日志支持，支持 JSON 和控制台两种输出格式。
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from ai_trading.config import LogFormat, get_settings


def _add_log_level(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """添加日志级别到事件字典。"""
    event_dict["level"] = method_name.upper()
    return event_dict


def _add_timestamp(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """添加时间戳到事件字典。"""
    # structlog 的 TimeStamper 会处理这个
    return event_dict


def setup_logging() -> None:
    """配置结构化日志系统。

    根据配置设置日志级别和输出格式。
    """
    settings = get_settings()

    # 设置标准库日志级别
    log_level = getattr(logging, settings.log_level)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # 共享处理器
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # 根据格式选择渲染器
    if settings.log_format == LogFormat.JSON:
        # JSON 格式输出
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # 控制台格式输出（带颜色）
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """获取结构化日志记录器。

    Args:
        name: 日志记录器名称。如果为 None，则使用调用模块名。

    Returns:
        结构化日志记录器实例。
    """
    return structlog.get_logger(name)


# 便捷日志函数
def log_trade_signal(
    logger: structlog.stdlib.BoundLogger,
    *,
    symbol: str,
    direction: str,
    signal_type: str,
    **kwargs: Any,
) -> None:
    """记录交易信号。"""
    logger.info(
        "trade_signal",
        symbol=symbol,
        direction=direction,
        signal_type=signal_type,
        **kwargs,
    )


def log_llm_call(
    logger: structlog.stdlib.BoundLogger,
    *,
    model: str,
    success: bool,
    latency_ms: float,
    **kwargs: Any,
) -> None:
    """记录 LLM 调用。"""
    level = "info" if success else "warning"
    getattr(logger, level)(
        "llm_call",
        model=model,
        success=success,
        latency_ms=round(latency_ms, 2),
        **kwargs,
    )


def log_order_execution(
    logger: structlog.stdlib.BoundLogger,
    *,
    symbol: str,
    side: str,
    quantity: float,
    price: float | None = None,
    order_id: str | None = None,
    status: str = "submitted",
    **kwargs: Any,
) -> None:
    """记录订单执行。"""
    logger.info(
        "order_execution",
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        order_id=order_id,
        status=status,
        **kwargs,
    )


def log_risk_event(
    logger: structlog.stdlib.BoundLogger,
    *,
    event_type: str,
    action: str,
    **kwargs: Any,
) -> None:
    """记录风控事件。"""
    logger.warning(
        "risk_event",
        event_type=event_type,
        action=action,
        **kwargs,
    )
