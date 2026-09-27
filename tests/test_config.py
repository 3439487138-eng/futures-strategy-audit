from pathlib import Path

from futures_audit.config import load_config


def test_contract_multipliers_and_no_credentials():
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "configs" / "base.toml")
    assert config["instruments"]["IF"]["multiplier"] == 300.0
    assert config["instruments"]["TF"]["multiplier"] == 10000.0
    assert config["instruments"]["T"]["multiplier"] == 10000.0
    assert config["instruments"]["CU"]["multiplier"] == 5.0
    assert config["instruments"]["RB"]["multiplier"] == 10.0
    assert "token" not in (root / "configs" / "base.toml").read_text(encoding="utf-8").lower()

