"""CLI 入口模块 - AI Trading System 命令行接口。"""

import sys
import time
from datetime import datetime
from typing import NoReturn

import click

from ai_trading import __version__
from ai_trading.config import get_settings
from ai_trading.pipeline import run_trading_cycle
from ai_trading.utils.logging import get_logger, setup_logging


@click.group(invoke_without_command=True)
@click.option("--version", "-v", is_flag=True, help="显示版本号")
@click.pass_context
def cli(ctx: click.Context, version: bool) -> None:
    """AI Trading System - AI 增强的加密货币波段交易系统。

    结合技术指标与 LLM 分析，实现 BTC/ETH 的 3-7 天持仓周期交易。
    """
    if version:
        click.echo(f"ai-trading version {__version__}")
        return

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="试运行模式，不执行实际操作",
)
def once(dry_run: bool) -> None:
    """执行单次交易循环。

    拉取数据 → 生成候选 → AI 决策 → 风控检查 → 执行/记录
    """
    setup_logging()
    logger = get_logger("ai_trading.main")
    settings = get_settings()

    # 确保目录存在
    settings.ensure_directories()

    logger.info(
        "starting_single_run",
        mode=settings.mode.value,
        dry_run=dry_run,
        timestamp=datetime.now().isoformat(),
    )

    # 验证配置
    if settings.is_live_mode:
        missing = settings.validate_for_live()
        if missing:
            logger.error(
                "missing_required_config",
                missing_keys=missing,
                hint="请在 .env 文件中配置必要的 API 密钥",
            )
            sys.exit(1)

    try:
        result = run_trading_cycle(settings, dry_run=dry_run)
        logger.info(
            "run_completed",
            status=result.status,
            elapsed_ms=round(result.elapsed_ms, 2),
            decisions=len(result.decisions),
            orders=len(result.orders),
            warnings=result.warnings,
        )

    except KeyboardInterrupt:
        logger.info("run_interrupted", message="User interrupted")
        sys.exit(0)
    except Exception as e:
        logger.exception("run_failed", error=str(e))
        sys.exit(1)


@cli.command()
@click.option(
    "--interval-min",
    "-i",
    type=int,
    default=15,
    help="循环间隔（分钟）",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="试运行模式，不执行实际操作",
)
def loop(interval_min: int, dry_run: bool) -> NoReturn:
    """循环执行交易循环。

    每隔指定时间执行一次完整的交易循环。
    使用 Ctrl+C 停止。
    """
    setup_logging()
    logger = get_logger("ai_trading.main")
    settings = get_settings()

    # 确保目录存在
    settings.ensure_directories()

    logger.info(
        "starting_loop",
        mode=settings.mode.value,
        interval_min=interval_min,
        dry_run=dry_run,
    )

    # 验证配置
    if settings.is_live_mode:
        missing = settings.validate_for_live()
        if missing:
            logger.error(
                "missing_required_config",
                missing_keys=missing,
                hint="请在 .env 文件中配置必要的 API 密钥",
            )
            sys.exit(1)

    iteration = 0
    interval_sec = interval_min * 60

    try:
        while True:
            iteration += 1
            logger.info(
                "loop_iteration_start",
                iteration=iteration,
                timestamp=datetime.now().isoformat(),
            )

            try:
                result = run_trading_cycle(settings, dry_run=dry_run)
                logger.info(
                    "loop_iteration_completed",
                    iteration=iteration,
                    status=result.status,
                    elapsed_ms=round(result.elapsed_ms, 2),
                    decisions=len(result.decisions),
                    orders=len(result.orders),
                    warnings=result.warnings,
                )

            except Exception as e:
                logger.exception(
                    "loop_iteration_failed",
                    iteration=iteration,
                    error=str(e),
                )
                # 继续循环，不因单次失败而退出

            # 等待下一次循环
            logger.debug(
                "waiting_next_iteration",
                wait_seconds=interval_sec,
                next_run=datetime.now().isoformat(),
            )
            time.sleep(interval_sec)

    except KeyboardInterrupt:
        logger.info(
            "loop_stopped",
            message="User stopped loop",
            total_iterations=iteration,
        )
        sys.exit(0)


@cli.command()
def status() -> None:
    """显示系统状态和配置摘要。"""
    setup_logging()
    settings = get_settings()

    click.echo("=" * 50)
    click.echo("AI Trading System - Status")
    click.echo("=" * 50)
    click.echo()

    # 运行模式
    mode_marker = "[PAPER]" if settings.is_paper_mode else "[LIVE]"
    mode_text = "Paper Trading" if settings.is_paper_mode else "Live Trading"
    click.echo(f"{mode_marker} Mode: {mode_text}")
    click.echo()

    # API 配置状态
    click.echo("[API Configuration]")
    binance_status = "[OK] Configured" if settings.binance_api_key else "[--] Not configured"
    openrouter_status = "[OK] Configured" if settings.openrouter_api_key else "[--] Not configured"
    click.echo(f"   Binance API: {binance_status}")
    click.echo(f"   OpenRouter API: {openrouter_status}")
    click.echo(f"   Binance Testnet: {'Yes' if settings.binance_testnet else 'No'}")
    click.echo(f"   LLM Model: {settings.openrouter_model}")
    click.echo()

    # 风控参数
    click.echo("[Risk Parameters]")
    click.echo(f"   Risk per trade: {settings.risk_per_trade_pct}%")
    click.echo(f"   Stop loss: {settings.stop_loss_atr_multiplier} ATR")
    click.echo(f"   Time stop: {settings.max_holding_days} days")
    click.echo(f"   Max consecutive losses: {settings.max_consecutive_losses}")
    click.echo(f"   Max weekly drawdown: {settings.max_weekly_drawdown_pct}%")
    click.echo()

    # 日志配置
    click.echo("[Logging]")
    click.echo(f"   Log level: {settings.log_level}")
    click.echo(f"   Log format: {settings.log_format.value}")
    click.echo(f"   Journal dir: {settings.journal_dir}")
    click.echo()

    # 验证状态
    if settings.is_live_mode:
        missing = settings.validate_for_live()
        if missing:
            click.echo("[ERROR] Live mode configuration incomplete, missing:")
            for key in missing:
                click.echo(f"   - {key}")
        else:
            click.echo("[OK] Live mode configuration complete")
    else:
        click.echo("[INFO] Paper mode does not require full API configuration")

    click.echo()
    click.echo("=" * 50)


@cli.command()
def check() -> None:
    """检查系统依赖和配置。"""
    setup_logging()
    logger = get_logger("ai_trading.main")

    click.echo("Checking system dependencies...")
    click.echo()

    all_ok = True

    # 检查必要的包
    packages = [
        ("pydantic", "Configuration validation"),
        ("httpx", "HTTP client"),
        ("pandas", "Data processing"),
        ("numpy", "Numerical computing"),
        ("structlog", "Structured logging"),
        ("click", "CLI framework"),
        ("tenacity", "Retry mechanism"),
    ]

    for pkg_name, desc in packages:
        try:
            __import__(pkg_name)
            click.echo(f"  [OK] {pkg_name} - {desc}")
        except ImportError:
            click.echo(f"  [MISSING] {pkg_name} - {desc}")
            all_ok = False

    click.echo()

    # 检查配置文件
    from pathlib import Path

    env_file = Path(".env")
    if env_file.exists():
        click.echo("  [OK] .env configuration file exists")
    else:
        click.echo("  [WARN] .env file not found (using defaults)")

    click.echo()

    if all_ok:
        click.echo("[OK] All dependency checks passed")
    else:
        click.echo("[ERROR] Some dependencies missing. Run: pip install -e .")

    logger.info("dependency_check_completed", all_ok=all_ok)


# 支持 python -m ai_trading.main 调用
if __name__ == "__main__":
    cli()
