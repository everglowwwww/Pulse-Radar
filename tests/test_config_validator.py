"""config_validator 单元测试。"""

import pytest
from src.config_validator import validate_config, sanitize_config


class TestValidateConfig:
    """validate_config 测试。"""

    def test_empty_config_is_valid(self):
        ok, errors = validate_config({})
        assert ok is True
        assert errors == []

    def test_valid_full_config(self):
        cfg = {
            "poll_interval": 10,
            "push_threshold": 60,
            "sensitivity": "high",
            "filters": {"min_market_cap": 2_000_000_000},
            "watchlist": {
                "stocks": [{"code": "603986", "name": "兆易创新"}],
                "push_threshold": 30,
            },
            "notifications": {"desktop": True, "sound": False},
            "output_dir": "~/Desktop/PulseRadar",
        }
        ok, errors = validate_config(cfg)
        assert ok is True
        assert errors == []

    def test_poll_interval_too_small(self):
        ok, errors = validate_config({"poll_interval": 1})
        assert ok is False
        assert any("poll_interval" in e for e in errors)

    def test_poll_interval_wrong_type(self):
        ok, errors = validate_config({"poll_interval": "fast"})
        assert ok is False
        assert any("poll_interval" in e and "整数" in e for e in errors)

    def test_push_threshold_out_of_range(self):
        ok, errors = validate_config({"push_threshold": 150})
        assert ok is False
        assert any("push_threshold" in e for e in errors)

    def test_invalid_sensitivity(self):
        ok, errors = validate_config({"sensitivity": "ultra"})
        assert ok is False
        assert any("sensitivity" in e for e in errors)

    def test_filters_non_numeric_value(self):
        ok, errors = validate_config({"filters": {"min_cap": "big"}})
        assert ok is False
        assert any("filters" in e for e in errors)

    def test_watchlist_stock_missing_code(self):
        ok, errors = validate_config({
            "watchlist": {"stocks": [{"name": "某股票"}]}
        })
        assert ok is False
        assert any("code" in e for e in errors)

    def test_multiple_errors_collected(self):
        ok, errors = validate_config({
            "poll_interval": 0,
            "sensitivity": "xxx",
            "push_threshold": -5,
        })
        assert ok is False
        assert len(errors) == 3


class TestSanitizeConfig:
    """sanitize_config 测试。"""

    def test_empty_fills_defaults(self):
        cfg = sanitize_config({})
        assert cfg["poll_interval"] == 5
        assert cfg["push_threshold"] == 60
        assert cfg["sensitivity"] == "medium"
        assert "notifications" in cfg
        assert "watchlist" in cfg

    def test_user_values_preserved(self):
        cfg = sanitize_config({"push_threshold": 80, "sensitivity": "high"})
        assert cfg["push_threshold"] == 80
        assert cfg["sensitivity"] == "high"
        # 其他字段用默认值
        assert cfg["poll_interval"] == 5

    def test_watchlist_stocks_preserved(self):
        stocks = [{"code": "603986", "name": "兆易创新"}]
        cfg = sanitize_config({"watchlist": {"stocks": stocks}})
        assert cfg["watchlist"]["stocks"] == stocks

    def test_does_not_mutate_input(self):
        original = {"push_threshold": 70}
        cfg = sanitize_config(original)
        cfg["push_threshold"] = 99
        assert original["push_threshold"] == 70  # 原始未变
