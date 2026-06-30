"""holidays 模块单元测试。"""

from datetime import date
from src.holidays import is_trading_day, next_trading_day


class TestIsTradingDay:
    """is_trading_day 测试。"""

    def test_weekday_normal(self):
        # 2025-06-30 周一，非节假日
        assert is_trading_day(date(2025, 6, 30)) is True

    def test_saturday(self):
        assert is_trading_day(date(2025, 6, 28)) is False

    def test_sunday(self):
        assert is_trading_day(date(2025, 6, 29)) is False

    def test_national_day(self):
        # 国庆节 10 月 1 日
        assert is_trading_day(date(2025, 10, 1)) is False

    def test_spring_festival(self):
        # 2025 春节 1月28日 - 2月4日
        assert is_trading_day(date(2025, 1, 29)) is False

    def test_new_year(self):
        # 元旦
        assert is_trading_day(date(2025, 1, 1)) is False

    def test_weekend_in_holiday_week(self):
        # 国庆假期中的周末
        assert is_trading_day(date(2025, 10, 4)) is False

    def test_regular_friday(self):
        # 2025-07-04 周五，不是节假日
        assert is_trading_day(date(2025, 7, 4)) is True


class TestNextTradingDay:
    """next_trading_day 测试。"""

    def test_friday_to_monday(self):
        # 2025-07-04 周五 → 下一个交易日是 2025-07-07 周一
        result = next_trading_day(date(2025, 7, 4))
        assert result == date(2025, 7, 7)

    def test_before_national_day(self):
        # 2025-09-30 周二 → 下一个交易日跳过国庆假期
        result = next_trading_day(date(2025, 9, 30))
        assert result > date(2025, 10, 1)  # 应该跳过整个假期
        assert result.weekday() < 5  # 应该落在工作日

    def test_regular_weekday(self):
        # 2025-06-30 周一 → 2025-07-01 周二
        result = next_trading_day(date(2025, 6, 30))
        assert result == date(2025, 7, 1)
