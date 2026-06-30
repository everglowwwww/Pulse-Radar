"""
holidays.py – 中国 A 股交易日历模块
======================================
维护 A 股市场已知的非交易日（法定节假日休市安排），
提供 is_trading_day / next_trading_day 两个核心查询函数。

数据来源：中国证监会每年年底发布的下一年休市安排公告。
2026 年日期为根据国务院假日办惯例预估，正式公告后需核实更新。
"""

from __future__ import annotations

import datetime
from typing import Optional, Set

# ────────────────────────────────────────────────────────────
# 2025 年 A 股休市安排（不含周末，仅列法定节假日休市日）
#   元旦          : 1 月 1 日
#   春节          : 1 月 28 日 – 2 月 4 日
#   清明节        : 4 月 4 日
#   劳动节        : 5 月 1 日 – 5 月 5 日
#   端午节        : 5 月 31 日 – 6 月 2 日
#   中秋+国庆     : 10 月 1 日 – 10 月 8 日
# ────────────────────────────────────────────────────────────
_HOLIDAYS_2025: Set[datetime.date] = {
    # 元旦
    datetime.date(2025, 1, 1),
    # 春节
    datetime.date(2025, 1, 28),
    datetime.date(2025, 1, 29),
    datetime.date(2025, 1, 30),
    datetime.date(2025, 1, 31),
    datetime.date(2025, 2, 1),
    datetime.date(2025, 2, 2),
    datetime.date(2025, 2, 3),
    datetime.date(2025, 2, 4),
    # 清明节
    datetime.date(2025, 4, 4),
    # 劳动节
    datetime.date(2025, 5, 1),
    datetime.date(2025, 5, 2),
    datetime.date(2025, 5, 3),
    datetime.date(2025, 5, 4),
    datetime.date(2025, 5, 5),
    # 端午节
    datetime.date(2025, 5, 31),
    datetime.date(2025, 6, 1),
    datetime.date(2025, 6, 2),
    # 中秋节 + 国庆节
    datetime.date(2025, 10, 1),
    datetime.date(2025, 10, 2),
    datetime.date(2025, 10, 3),
    datetime.date(2025, 10, 4),
    datetime.date(2025, 10, 5),
    datetime.date(2025, 10, 6),
    datetime.date(2025, 10, 7),
    datetime.date(2025, 10, 8),
}

# ────────────────────────────────────────────────────────────
# 2026 年 A 股休市安排（预估，正式公告后需核实）
#   元旦          : 1 月 1 日 – 1 月 2 日
#   春节          : 2 月 17 日 – 2 月 23 日
#   清明节        : 4 月 5 日 – 4 月 6 日
#   劳动节        : 5 月 1 日 – 5 月 5 日
#   端午节        : 6 月 19 日
#   中秋节        : 9 月 25 日
#   国庆节        : 10 月 1 日 – 10 月 7 日
# ────────────────────────────────────────────────────────────
_HOLIDAYS_2026: Set[datetime.date] = {
    # 元旦
    datetime.date(2026, 1, 1),
    datetime.date(2026, 1, 2),
    # 春节
    datetime.date(2026, 2, 17),
    datetime.date(2026, 2, 18),
    datetime.date(2026, 2, 19),
    datetime.date(2026, 2, 20),
    datetime.date(2026, 2, 21),
    datetime.date(2026, 2, 22),
    datetime.date(2026, 2, 23),
    # 清明节
    datetime.date(2026, 4, 5),
    datetime.date(2026, 4, 6),
    # 劳动节
    datetime.date(2026, 5, 1),
    datetime.date(2026, 5, 2),
    datetime.date(2026, 5, 3),
    datetime.date(2026, 5, 4),
    datetime.date(2026, 5, 5),
    # 端午节
    datetime.date(2026, 6, 19),
    # 中秋节
    datetime.date(2026, 9, 25),
    # 国庆节
    datetime.date(2026, 10, 1),
    datetime.date(2026, 10, 2),
    datetime.date(2026, 10, 3),
    datetime.date(2026, 10, 4),
    datetime.date(2026, 10, 5),
    datetime.date(2026, 10, 6),
    datetime.date(2026, 10, 7),
}

# 合并所有已知节假日
HOLIDAYS: Set[datetime.date] = _HOLIDAYS_2025 | _HOLIDAYS_2026


def _today() -> datetime.date:
    """返回当天日期，便于测试时 mock。"""
    return datetime.date.today()


def is_trading_day(date: Optional[datetime.date] = None) -> bool:
    """
    判断给定日期是否为 A 股交易日。

    规则：
      1. 周六、周日不交易。
      2. 法定节假日休市期间不交易（见上方硬编码集合）。

    Parameters
    ----------
    date : datetime.date, optional
        待判断的日期，默认为今天。

    Returns
    -------
    bool
        True 表示是交易日，False 表示非交易日。
    """
    if date is None:
        date = _today()

    # 周末判断：周六 = 5, 周日 = 6
    if date.weekday() >= 5:
        return False

    # 节假日判断
    if date in HOLIDAYS:
        return False

    return True


def next_trading_day(date: Optional[datetime.date] = None) -> datetime.date:
    """
    返回给定日期之后的下一个交易日（不含当天）。

    Parameters
    ----------
    date : datetime.date, optional
        起始日期，默认为今天。

    Returns
    -------
    datetime.date
        下一个交易日的日期。
    """
    if date is None:
        date = _today()

    candidate = date + datetime.timedelta(days=1)
    # 最多向前查找 30 天（正常情况下不会超过，春节最长连休约 9 天）
    for _ in range(30):
        if is_trading_day(candidate):
            return candidate
        candidate += datetime.timedelta(days=1)

    # 理论上不应到达此处；若到达，直接返回候选日期并由调用方处理
    return candidate
