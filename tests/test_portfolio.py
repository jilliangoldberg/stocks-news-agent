import json
import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
if "anthropic" not in sys.modules:
    sys.modules["anthropic"] = types.SimpleNamespace(Anthropic=object)
import agent


def test_validate_portfolio_allocations_accepts_valid_100_percent():
    portfolio = {
        "positions": [
            {"ticker": "AAPL", "allocation_pct": 60.0},
            {"ticker": "VOO", "allocation_pct": 40.0},
        ]
    }
    agent.validate_portfolio_allocations(portfolio)


def test_validate_portfolio_allocations_rejects_total_not_100():
    portfolio = {
        "positions": [
            {"ticker": "AAPL", "allocation_pct": 60.0},
            {"ticker": "VOO", "allocation_pct": 30.0},
        ]
    }
    with pytest.raises(ValueError, match="must equal 100%"):
        agent.validate_portfolio_allocations(portfolio)


def test_validate_portfolio_allocations_rejects_negative_allocation():
    portfolio = {
        "positions": [
            {"ticker": "AAPL", "allocation_pct": 110.0},
            {"ticker": "VOO", "allocation_pct": -10.0},
        ]
    }
    with pytest.raises(ValueError, match="negative allocation"):
        agent.validate_portfolio_allocations(portfolio)


def test_validate_portfolio_allocations_rejects_missing_numeric_allocation():
    portfolio = {
        "positions": [
            {"ticker": "AAPL", "allocation_pct": "50"},
            {"ticker": "VOO", "allocation_pct": 50.0},
        ]
    }
    with pytest.raises(ValueError, match="missing numeric 'allocation_pct'"):
        agent.validate_portfolio_allocations(portfolio)


def test_validate_portfolio_allocations_rejects_empty_ticker():
    portfolio = {
        "positions": [
            {"ticker": "AAPL", "allocation_pct": 50.0},
            {"ticker": "", "allocation_pct": 50.0},
        ]
    }
    with pytest.raises(ValueError, match="non-empty 'ticker'"):
        agent.validate_portfolio_allocations(portfolio)


def test_load_portfolio_reads_from_portfolio_file(tmp_path, monkeypatch):
    portfolio_path = tmp_path / "portfolio.json"
    file_portfolio = {
        "positions": [
            {"ticker": "QQQ", "allocation_pct": 70.0},
            {"ticker": "BND", "allocation_pct": 30.0},
        ],
        "themes": ["growth"],
        "risk_level": "medium",
    }
    portfolio_path.write_text(json.dumps(file_portfolio), encoding="utf-8")

    monkeypatch.setattr(agent, "PORTFOLIO_DIR", str(tmp_path / "portfolio"))
    monkeypatch.setattr(agent, "PORTFOLIO_FILE", str(portfolio_path))
    loaded = agent.load_portfolio()

    assert loaded == file_portfolio


def test_load_portfolio_falls_back_to_default_when_file_missing(monkeypatch):
    fallback_portfolio = {
        "positions": [
            {"ticker": "AAPL", "allocation_pct": 55.0},
            {"ticker": "VOO", "allocation_pct": 45.0},
        ],
        "themes": ["core"],
        "risk_level": "low",
    }

    monkeypatch.setattr(agent, "PORTFOLIO_DIR", "/tmp/path/that/does/not/exist_dir")
    monkeypatch.setattr(agent, "PORTFOLIO_FILE", "/tmp/path/that/does/not/exist.json")
    monkeypatch.setattr(agent, "PORTFOLIO", fallback_portfolio)

    loaded = agent.load_portfolio()
    assert loaded == fallback_portfolio


def test_validate_portfolio_allocations_accepts_multi_account():
    multi_account_portfolio = {
        "accounts": [
            {
                "name": "taxable",
                "positions": [
                    {"ticker": "AAPL", "allocation_pct": 70.0},
                    {"ticker": "VOO", "allocation_pct": 30.0},
                ],
            },
            {
                "name": "retirement",
                "positions": [
                    {"ticker": "QQQ", "allocation_pct": 60.0},
                    {"ticker": "BND", "allocation_pct": 40.0},
                ],
            },
        ]
    }
    agent.validate_portfolio_allocations(multi_account_portfolio)


def test_load_portfolio_reads_accounts_from_portfolio_directory(tmp_path, monkeypatch):
    portfolio_dir = tmp_path / "portfolio"
    portfolio_dir.mkdir()

    (portfolio_dir / "taxable.json").write_text(
        json.dumps(
            {
                "name": "taxable",
                "positions": [
                    {"ticker": "AAPL", "allocation_pct": 50.0},
                    {"ticker": "VOO", "allocation_pct": 50.0},
                ],
                "themes": ["core"],
                "risk_level": "medium",
            }
        ),
        encoding="utf-8",
    )
    (portfolio_dir / "retirement.json").write_text(
        json.dumps(
            {
                "name": "retirement",
                "positions": [
                    {"ticker": "QQQ", "allocation_pct": 60.0},
                    {"ticker": "BND", "allocation_pct": 40.0},
                ],
                "themes": ["indexing"],
                "risk_level": "low",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(agent, "PORTFOLIO_DIR", str(portfolio_dir))
    monkeypatch.setattr(agent, "PORTFOLIO_FILE", str(tmp_path / "portfolio.json"))

    loaded = agent.load_portfolio()

    assert len(loaded["accounts"]) == 2
    assert loaded["themes"] == ["core", "indexing"]
    assert loaded["risk_level"] == "mixed"
