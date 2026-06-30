"""
PulseRadar — 自选股实时行情播报 + 买点分析模块
每轮扫描后推送自选股行情快照，含多维度买点判断。
不走异动评分逻辑，不受冷却去重限制。
"""

import logging
import time
from datetime import datetime

import pandas as pd

from .notifier import send_desktop_notification

logger = logging.getLogger(__name__)


def _safe(val, default=0):
    """安全取值，None/NaN → default。"""
    if val is None:
        return default
    try:
        if pd.isna(val):
            return default
    except (TypeError, ValueError):
        pass
    return val


def _format_amount(val: float) -> str:
    """金额格式化：亿/万。"""
    val = abs(val)
    if val >= 1e8:
        return f"{val / 1e8:.1f}亿"
    if val >= 1e4:
        return f"{val / 1e4:.0f}万"
    return f"{val:.0f}"


# ─── 买点分析逻辑 ───


def _analyze_entry_point(row: pd.Series) -> dict:
    """
    对单只自选股做多维度买点分析。

    综合考虑 7 个维度，每个维度打正/负分，最终汇总为建议。
    返回 {verdict, score, reasons: [str], cautions: [str]}
    """
    score = 0
    reasons: list[str] = []    # 正面因素
    cautions: list[str] = []   # 风险提示

    change_pct = _safe(row.get("涨跌幅"))
    volume_ratio = _safe(row.get("量比"))
    turnover_rate = _safe(row.get("换手率"))
    turnover = _safe(row.get("成交额"))
    price = _safe(row.get("最新价"))
    high = _safe(row.get("最高"))
    low = _safe(row.get("最低"))
    open_ = _safe(row.get("今开"))
    pre_close = _safe(row.get("昨收"))
    speed = _safe(row.get("涨速"))
    five_min = _safe(row.get("5分钟涨跌"))
    pe = _safe(row.get("市盈率-动态"))
    net_inflow = _safe(row.get("主力净流入"))  # 东方财富可能有

    # ── 1. 涨跌幅位置 ──
    if -1.0 <= change_pct <= 2.0:
        score += 2
        reasons.append("涨幅温和，追高风险低")
    elif 2.0 < change_pct <= 5.0:
        score += 1
        reasons.append("上涨趋势中，动能尚存")
    elif change_pct > 7.0:
        score -= 2
        cautions.append(f"涨幅已达 {change_pct:+.1f}%，追高风险较大")
    elif change_pct < -3.0:
        score -= 1
        cautions.append(f"下跌 {change_pct:.1f}%，注意趋势")

    # ── 2. 量比（资金参与度） ──
    if 1.5 <= volume_ratio <= 5.0:
        score += 2
        reasons.append(f"量比 {volume_ratio:.1f} 放量配合")
    elif volume_ratio > 5.0:
        score += 1
        reasons.append(f"量比 {volume_ratio:.1f} 极端放量，关注是否为拉高出货")
        cautions.append("极端放量需警惕主力对倒")
    elif volume_ratio < 0.8:
        score -= 1
        cautions.append(f"量比 {volume_ratio:.1f} 缩量，市场关注度低")

    # ── 3. 换手率 ──
    if 2.0 <= turnover_rate <= 8.0:
        score += 1
        reasons.append(f"换手率 {turnover_rate:.1f}%，流动性良好")
    elif turnover_rate > 15.0:
        score -= 1
        cautions.append(f"换手率 {turnover_rate:.1f}% 过高，筹码松动")
    elif turnover_rate < 0.5:
        cautions.append(f"换手率 {turnover_rate:.2f}% 极低，流动性差")

    # ── 4. 分时强度（价格在日内位置） ──
    if high > low > 0:
        day_range = high - low
        if day_range > 0:
            position = (price - low) / day_range  # 0=日内最低, 1=日内最高
            if position >= 0.7:
                score += 1
                reasons.append("股价在日内高位运行，多头占优")
            elif position <= 0.3:
                if change_pct >= 0:
                    score += 1
                    reasons.append("回踩日内低位但未翻绿，可能有支撑")
                else:
                    cautions.append("弱势运行在日内低位")

    # ── 5. 涨速/动能 ──
    if speed > 2.0:
        score += 1
        reasons.append(f"涨速 {speed:+.1f}%/min 正在加速")
    elif speed < -2.0:
        score -= 1
        cautions.append(f"涨速 {speed:+.1f}%/min 正在快速回落")

    # ── 6. 5 分钟涨跌趋势 ──
    if five_min > 1.0:
        score += 1
        reasons.append(f"近 5 分钟上涨 {five_min:+.1f}%，短线动能向上")
    elif five_min < -1.5:
        score -= 1
        cautions.append(f"近 5 分钟下跌 {five_min:.1f}%，短线承压")

    # ── 7. 资金流向（如果有数据） ──
    if net_inflow:
        if net_inflow > 0:
            score += 1
            reasons.append(f"主力净流入 {_format_amount(net_inflow)}")
        elif net_inflow < -5_000_000:
            score -= 1
            cautions.append(f"主力净流出 {_format_amount(net_inflow)}")

    # ── 综合判断 ──
    if score >= 4:
        verdict = "🟢 多维共振，可考虑介入"
    elif score >= 2:
        verdict = "🟡 条件尚可，建议观察确认"
    elif score >= 0:
        verdict = "⚪ 信号中性，暂无明确方向"
    else:
        verdict = "🔴 风险偏高，建议观望"

    return {
        "verdict": verdict,
        "score": score,
        "reasons": reasons,
        "cautions": cautions,
    }


# ─── 行情播报 ───


def generate_watchlist_report(
    market_df: pd.DataFrame,
    watch_codes: set[str],
) -> list[dict]:
    """
    为自选股生成实时行情快照 + 买点分析。

    参数:
        market_df: 全市场行情 DataFrame
        watch_codes: 自选股代码集合

    返回:
        每只自选股的行情报告 list[dict]
    """
    if not watch_codes or "代码" not in market_df.columns:
        return []

    watch_df = market_df[market_df["代码"].isin(watch_codes)]
    if watch_df.empty:
        return []

    reports = []
    for _, row in watch_df.iterrows():
        code = row.get("代码", "")
        name = row.get("名称", "")
        price = _safe(row.get("最新价"))
        change_pct = _safe(row.get("涨跌幅"))
        volume_ratio = _safe(row.get("量比"))
        turnover_rate = _safe(row.get("换手率"))
        turnover = _safe(row.get("成交额"))
        volume = _safe(row.get("成交量"))
        high = _safe(row.get("最高"))
        low = _safe(row.get("最低"))
        speed = _safe(row.get("涨速"))

        analysis = _analyze_entry_point(row)

        reports.append({
            "code": code,
            "name": name,
            "price": price,
            "change_pct": change_pct,
            "volume_ratio": volume_ratio,
            "turnover_rate": turnover_rate,
            "turnover": turnover,
            "volume": volume,
            "high": high,
            "low": low,
            "speed": speed,
            "analysis": analysis,
        })

    # 按涨跌幅排序
    reports.sort(key=lambda x: x["change_pct"], reverse=True)
    return reports


def _format_volume(vol: float) -> str:
    """成交量格式化：万手/手。"""
    if vol >= 10000:
        return f"{vol / 10000:.1f}万手"
    return f"{vol:.0f}手"


def push_watchlist_report(reports: list[dict]):
    """
    将自选股行情快照推送为桌面通知。
    每只股票一条独立通知，确保信息清晰完整。
    最后再推一条汇总通知。
    """
    if not reports:
        return

    now_str = datetime.now().strftime("%H:%M")

    for r in reports:
        name = r["name"]
        code = r["code"]
        price = r["price"]
        change_pct = r["change_pct"]
        volume_ratio = r["volume_ratio"]
        turnover_rate = r["turnover_rate"]
        turnover = r["turnover"]
        volume = r.get("volume", 0)
        speed = r["speed"]
        analysis = r["analysis"]

        sign = "+" if change_pct > 0 else ""

        title = f"⭐ {name} {sign}{change_pct:.2f}% · {price:.2f}"

        lines = []
        # 行情数据行：成交量 + 成交额 + 量比 + 换手率
        lines.append(
            f"成交 {_format_volume(volume)} · {_format_amount(turnover)} | "
            f"量比 {volume_ratio:.1f} | 换手 {turnover_rate:.1f}%"
        )
        if speed and abs(speed) >= 0.5:
            lines.append(f"涨速 {speed:+.1f}%/min")

        # 买点分析
        lines.append(f"—— {analysis['verdict']}")
        if analysis["reasons"]:
            lines.append(f"✅ {analysis['reasons'][0]}")
        if analysis["cautions"]:
            lines.append(f"⚠️ {analysis['cautions'][0]}")

        message = "\n".join(lines)
        send_desktop_notification(title, message, "info")

    # 汇总通知
    if len(reports) > 1:
        summary_lines = []
        for r in reports:
            sign = "+" if r["change_pct"] > 0 else ""
            v = r["analysis"]["verdict"].split("，")[0]
            summary_lines.append(
                f"{r['name']} {sign}{r['change_pct']:.2f}% "
                f"({r['price']:.2f}) {v}"
            )
        title = f"⭐ 自选股行情 · {now_str}"
        message = "\n".join(summary_lines)
        send_desktop_notification(title, message, "info")
