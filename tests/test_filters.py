"""filters 模块单元测试。"""

import pandas as pd
from src.filters import apply_filters


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """构造模拟的行情 DataFrame。"""
    defaults = {
        "代码": "000001", "名称": "测试股",
        "流通市值": 5_000_000_000, "成交额": 100_000_000,
        "换手率": 2.0, "涨跌幅": 3.0,
    }
    full_rows = [{**defaults, **r} for r in rows]
    return pd.DataFrame(full_rows)


class TestApplyFilters:
    """apply_filters 测试。"""

    def test_exclude_st(self):
        df = _make_df([
            {"名称": "平安银行", "代码": "000001"},
            {"名称": "ST某股", "代码": "000002"},
            {"名称": "*ST退市", "代码": "000003"},
        ])
        result, filtered = apply_filters(df, {"filters": {"exclude_st": True}})
        assert len(result) == 1
        assert result.iloc[0]["名称"] == "平安银行"
        assert filtered == 2

    def test_min_market_cap(self):
        df = _make_df([
            {"流通市值": 10_000_000_000},
            {"流通市值": 500_000_000},
        ])
        config = {"filters": {"min_market_cap": 2_000_000_000, "exclude_st": False}}
        result, filtered = apply_filters(df, config)
        assert len(result) == 1
        assert filtered == 1

    def test_min_daily_turnover(self):
        df = _make_df([
            {"成交额": 200_000_000},
            {"成交额": 10_000_000},
        ])
        config = {"filters": {"min_daily_turnover": 50_000_000, "exclude_st": False}}
        result, filtered = apply_filters(df, config)
        assert len(result) == 1

    def test_min_turnover_rate(self):
        df = _make_df([
            {"换手率": 3.0},
            {"换手率": 0.1},
        ])
        config = {"filters": {"min_turnover_rate": 0.3, "exclude_st": False}}
        result, filtered = apply_filters(df, config)
        assert len(result) == 1

    def test_exclude_limit_up(self):
        """涨停的票（涨幅 >= 9.8%）应被过滤。"""
        df = _make_df([
            {"涨跌幅": 5.0, "代码": "000001"},
            {"涨跌幅": 10.0, "代码": "000002"},  # 涨停
        ])
        config = {"filters": {"exclude_st": False, "min_market_cap": 0,
                               "min_daily_turnover": 0, "min_turnover_rate": 0}}
        result, _ = apply_filters(df, config)
        assert len(result) == 1
        assert result.iloc[0]["涨跌幅"] == 5.0

    def test_gem_20pct_limit(self):
        """创业板 (30x) 用 20% 涨跌幅限制。"""
        df = _make_df([
            {"涨跌幅": 15.0, "代码": "300001"},  # 创业板 15% 不算涨停
            {"涨跌幅": 20.0, "代码": "300002"},  # 创业板 20% 涨停
        ])
        config = {"filters": {"exclude_st": False, "min_market_cap": 0,
                               "min_daily_turnover": 0, "min_turnover_rate": 0}}
        result, _ = apply_filters(df, config)
        assert len(result) == 1
        assert result.iloc[0]["代码"] == "300001"

    def test_no_filters_returns_all(self):
        df = _make_df([{} for _ in range(5)])
        config = {"filters": {"exclude_st": False, "min_market_cap": 0,
                               "min_daily_turnover": 0, "min_turnover_rate": 0}}
        result, filtered = apply_filters(df, config)
        assert len(result) == 5
        assert filtered == 0
