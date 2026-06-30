"""
PulseRadar — 综合评分系统
根据信号类型、强度和置信度因子计算最终异动分数 (0-100)。
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 信号基础分配置
# 基础分 × 强度系数 = 该信号的原始得分
SIGNAL_BASE_SCORES = {
    # P0 核心信号
    "涨速异动": 40,     # 核心触发条件，基础分最高
    "量比突变": 25,     # 放量作为辅助确认，单独触发得分较低
    "涨停封板": 50,     # 涨停是强信号
    "涨停炸板": 35,     # 炸板是警告信号
    # P1 增强信号
    "板块共振": 15,     # 作为辅助信号，提升其他信号的置信度
    "封单强度": 12,     # 涨停板辅助判断
    "连板梯队": 10,     # 市场情绪参考
    "VWAP突破": 30,     # 机构级基准信号，基础分较高
    # 自选股特殊信号
    "目标价到达": 90,   # 用户设定的价位，高优先
    "止损预警": 95,     # 止损警报，最高优先
}


def calculate_confidence(stock_data: dict, signals: list[dict]) -> float:
    """
    计算置信度调整系数。
    
    参数:
        stock_data: 个股行情数据（字典形式的 row）
        signals: 该股票触发的所有信号
    
    返回:
        置信度系数（0.1 ~ 2.0）
    """
    confidence = 1.0
    
    # 正向因子
    market_cap = stock_data.get("流通市值", 0) or 0
    if market_cap > 5_000_000_000:  # 50 亿以上
        confidence *= 1.10
    
    volume_ratio = stock_data.get("量比", 0) or 0
    if volume_ratio > 5.0:  # 强放量
        confidence *= 1.10
    
    # 多信号共振加成
    if len(signals) >= 2:
        confidence *= 1.0 + 0.10 * (len(signals) - 1)
    
    # 负向因子
    if market_cap > 0 and market_cap < 3_000_000_000:  # 30 亿以下
        confidence *= 0.90
    
    turnover_rate = stock_data.get("换手率", 0) or 0
    if turnover_rate < 1.0 and volume_ratio < 2.0:
        # 换手率极低 + 量比不高 → 庄股特征
        confidence *= 0.70
    
    # 尾盘时段降权
    now = datetime.now()
    if now.hour == 14 and now.minute >= 30:
        confidence *= 0.80
    
    # 限制范围
    return max(0.1, min(2.0, confidence))


def score_signals(
    signals: list[dict],
    stock_data: dict,
) -> float:
    """
    计算单只股票的综合异动分数。
    
    参数:
        signals: 触发的信号列表
        stock_data: 个股行情数据
    
    返回:
        最终异动分数 (0-100)
    """
    if not signals:
        return 0.0
    
    # 计算各信号的得分，取最高分作为基础，其余信号叠加加成
    signal_scores = []
    for signal in signals:
        sig_type = signal.get("signal_type", "")
        strength = signal.get("strength", 1.0)
        base = SIGNAL_BASE_SCORES.get(sig_type, 10)
        
        # 强度系数：strength=1.0 → ×1.0, strength=2.0 → ×1.4, strength=3.0 → ×1.7
        # 使用递减收益曲线，避免极端强度导致分数爆炸
        strength_multiplier = 1.0 + 0.4 * min(strength - 1.0, 2.0) if strength > 1.0 else max(strength, 0.3)
        
        signal_scores.append(base * strength_multiplier)
    
    # 主信号取最高分，附加信号各贡献 30% 的叠加
    signal_scores.sort(reverse=True)
    raw_score = signal_scores[0]
    for extra_score in signal_scores[1:]:
        raw_score += extra_score * 0.30
    
    # 置信度调整
    confidence = calculate_confidence(stock_data, signals)
    final_score = raw_score * confidence
    
    # 裁剪到 0-100
    return max(0.0, min(100.0, final_score))


def merge_signals(signals: list[dict], stock_data: dict, score: float) -> dict:
    """
    将多个信号合并为一个完整的异动记录。
    
    参数:
        signals: 触发的信号列表
        stock_data: 个股行情数据
        score: 计算好的异动分数
    
    返回:
        完整的异动记录字典
    """
    # 选择最强信号作为主信号类型
    primary_signal = max(signals, key=lambda s: s.get("strength", 0))
    
    # 合并所有原因
    all_reasons = []
    for sig in signals:
        all_reasons.extend(sig.get("reasons", []))
    
    return {
        "stock_code": stock_data.get("代码", ""),
        "stock_name": stock_data.get("名称", ""),
        "signal_type": primary_signal.get("signal_type", "异动"),
        "score": round(score, 1),
        "price": stock_data.get("最新价", 0),
        "change_pct": stock_data.get("涨跌幅", 0),
        "volume_ratio": stock_data.get("量比", 0),
        "turnover_rate": stock_data.get("换手率", 0),
        "market_cap": stock_data.get("流通市值", 0),
        "reasons": all_reasons,
        "signal_count": len(signals),
        "timestamp": datetime.now().isoformat(),
        "notified": False,
    }
