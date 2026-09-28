import pandas as pd

from futures_audit.report import _git_sha, _svg_series


def test_svg_series_is_embedded():
    nav = pd.DataFrame({"equity": [100.0, 101.0, 99.0]})
    chart = _svg_series(nav, "equity", "Equity", "#000")
    assert "<svg" in chart
    assert "https://" not in chart


def test_git_sha_prefers_valid_actions_environment(monkeypatch, tmp_path):
    sha = "a" * 40
    monkeypatch.setenv("GITHUB_SHA", sha.upper())
    assert _git_sha(tmp_path) == sha


def test_git_sha_rejects_non_sha_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_SHA", "not-a-commit")
    assert _git_sha(tmp_path) == "uncommitted-local-run"
