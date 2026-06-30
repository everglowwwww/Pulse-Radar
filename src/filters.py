"""
PulseRadar — 基础过滤器
排除不符合条件的股票，降低信号噪音。
注意：自选股盯梢模式不受过滤器限制。
"""

import pandas as pd


def apply_filters(df: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, int]:
    """
    对全市场行情 DataFrame 应用基础过滤器。
    
    参数:
        df: stock_zh_a_spot_em() 返回的 DataFrame
        config: config.json 中的 filters 配置
    
    返回:
        (过滤后的 DataFrame, 被过滤掉的数量)
    """
    filters = config.get("filters", {})
    original_count = len(df)
    
    # 1. 排除 ST/*ST 股票
    if filters.get("exclude_st", True):
        st_mask = df["名称"].str.contains(r"^(?:\*?ST|S)", na=False)
        df = df[~st_mask]
    
    # 2. 排除流通市值过小的股票
    min_cap = filters.get("min_market_cap", 2_000_000_000)
    if "流通市值" in df.columns:
        df = df[df["流通市值"].fillna(0) >= min_cap]
    
    # 3. 排除日成交额过低的股票
    min_turnover = filters.get("min_daily_turnover", 50_000_000)
    if "成交额" in df.columns:
        df = df[df["成交额"].fillna(0) >= min_turnover]
    
    # 4. 排除换手率过低的股票
    min_rate = filters.get("min_turnover_rate", 0.3)
    if "换手率" in df.columns:
        df = df[df["换手率"].fillna(0) >= min_rate]
    
    # 5. 排除已涨停/跌停的股票（主板 ±10%，创业板/科创板 ±20%）
    if "涨跌幅" in df.columns and "代码" in df.columns:
        def get_limit(code: str) -> float:
            if code.startswith(("30", "68")):  # 创业板/科创板
                return 19.8
            return 9.8
        
        limits = df["代码"].apply(get_limit)
        change_pct = df["涨跌幅"].fillna(0).abs()
        df = df[change_pct < limits]
    
    filtered_count = original_count - len(df)
    return df, filtered_count
