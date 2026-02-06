from click.testing import CliRunner

from ai_trading.main import cli
from ai_trading.types import CycleResult


def test_cli_once_smoke(monkeypatch: object) -> None:
    def _fake_run_cycle(settings: object, dry_run: bool) -> CycleResult:
        return CycleResult(status="ok", elapsed_ms=1.0)

    monkeypatch.setattr("ai_trading.main.run_trading_cycle", _fake_run_cycle)
    runner = CliRunner()
    result = runner.invoke(cli, ["once", "--dry-run"])
    assert result.exit_code == 0
