"""
PulseRadar — 信号检测模块
实现 P0 核心信号检测：涨速异动、量比突变、涨停/炸板监控。
"""

import logging
from datetime import datetime

import pandas as pd

from .signals_p1 import VWAPDetector

logger = logging.getLogger(__name__)


class SignalDetector:
    """P0 核心信号检测器。"""
    
    def __init__(self, config: dict):
        self.config = config
        # 涨速阈值（%/min），默认 2
        self.speed_threshold = 2.0
        # 5 分钟涨幅阈值（%），默认 3
        self.five_min_threshold = 3.0
        # 量比放量阈值
        self.volume_ratio_threshold = 1.5  # 涨速异动需同时满足
        self.volume_ratio_significant = 3.0  # 独立触发：显著放量
        self.volume_ratio_extreme = 8.0  # 独立触发：极端放量
        
        # P1 信号检测器
        self.vwap_detector = VWAPDetector()
        
        # 根据灵敏度调整阈值
        sensitivity = config.get("sensitivity", "medium")
        if sensitivity == "high":
            self.speed_threshold = 1.5
            self.five_min_threshold = 2.0
            self.volume_ratio_significant = 2.5
        elif sensitivity == "low":
            self.speed_threshold = 3.0
            self.five_min_threshold = 4.0
            self.volume_ratio_significant = 4.0
    
    def detect_speed_anomaly(self, row: pd.Series) -> dict | None:
        """
        检测涨速异动。
        触发条件：涨速 > 阈值 或 5分钟涨幅 > 阈值，且量比 > 1.5
        """
        speed = row.get("涨速", 0) or 0
        five_min_change = row.get("5分钟涨跌", 0) or 0
        volume_ratio = row.get("量比", 0) or 0
        
        # 量比必须达标
        if volume_ratio < self.volume_ratio_threshold:
            return None
        
        reasons = []
        strength = 0.0
        
        if abs(speed) >= self.speed_threshold:
            strength = min(abs(speed) / self.speed_threshold, 3.0)  # 上限 3 倍
            reasons.append(f"涨速 {speed:+.1f}%/min")
        
        if abs(five_min_change) >= self.five_min_threshold:
            five_strength = min(abs(five_min_change) / self.five_min_threshold, 3.0)
            strength = max(strength, five_strength)
            reasons.append(f"5分钟 {five_min_change:+.1f}%")
        
        if not reasons:
            return None
        
        reasons.append(f"量比 {volume_ratio:.1f}")
        
        return {
            "signal_type": "涨速异动",
            "strength": strength,
            "reasons": reasons,
            "raw_data": {
                "speed": speed,
                "five_min_change": five_min_change,
                "volume_ratio": volume_ratio,
            }
        }
    
    def detect_volume_surge(self, row: pd.Series) -> dict | None:
        """
        检测量比突变。
        独立检测：量比 > 3（显著放量）或 > 8（极端放量）。
        用于发现"突然放量但涨幅尚不明显"的早期信号。
        """
        volume_ratio = row.get("量比", 0) or 0
        
        if volume_ratio < self.volume_ratio_significant:
            return None
        
        # 计算信号强度
        if volume_ratio >= self.volume_ratio_extreme:
            strength = 3.0  # 极端放量
            label = "极端放量"
        elif volume_ratio >= 5.0:
            strength = 2.0
            label = "强放量"
        else:
            strength = 1.0
            label = "显著放量"
        
        return {
            "signal_type": "量比突变",
            "strength": strength,
            "reasons": [f"{label} 量比 {volume_ratio:.1f}"],
            "raw_data": {
                "volume_ratio": volume_ratio,
            }
        }
    
    def detect_all(self, row: pd.Series) -> list[dict]:
        """
        对单只股票运行所有 P0 信号检测。
        
        返回:
            触发的信号列表（可能有多个）
        """
        signals = []
        
        # 涨速异动
        speed_signal = self.detect_speed_anomaly(row)
        if speed_signal:
            signals.append(speed_signal)
        
        # 量比突变（独立信号，与涨速异动可共存）
        volume_signal = self.detect_volume_surge(row)
        if volume_signal:
            # 如果已经有涨速异动信号（其中已包含量比信息），
            # 只在量比达到“极端”级别时才作为独立信号
            if speed_signal and volume_signal["strength"] < 2.0:
                pass  # 低级别量比已被涨速异动覆盖
            else:
                signals.append(volume_signal)
        
        # P1: VWAP 突破检测
        vwap_signal = self.vwap_detector.detect(row)
        if vwap_signal:
            signals.append(vwap_signal)
        
        return signals


class LimitDetector:
    """涨停板/炸板监控器。"""
    
    def __init__(self):
        # 已知涨停股票集合（用于检测新增涨停）
        self._known_zt_stocks: set[str] = set()
        # 已知炸板股票集合（用于炸板去重）
        self._known_zb_stocks: set[str] = set()
    
    def detect_limit_changes(
        self,
        current_zt: pd.DataFrame | None,
        current_zb: pd.DataFrame | None,
    ) -> list[dict]:
        """
        检测涨停/炸板变化。
        
        参数:
            current_zt: stock_zt_pool_em() 返回的涨停股池
            current_zb: stock_zt_pool_zbgc_em() 返回的炸板股池
        
        返回:
            变化信号列表
        """
        signals = []
        
        if current_zt is not None and not current_zt.empty:
            current_codes = set(current_zt["代码"].tolist()) if "代码" in current_zt.columns else set()
            
            # 新增涨停
            new_zt = current_codes - self._known_zt_stocks
            for code in new_zt:
                row = current_zt[current_zt["代码"] == code].iloc[0] if "代码" in current_zt.columns else None
                if row is not None:
                    name = row.get("名称", "未知")
                    seal_money = row.get("封板资金", 0)
                    first_time = row.get("首次封板时间", "")
                    chain_count = row.get("涨停统计", "")
                    
                    signals.append({
                        "signal_type": "涨停封板",
                        "stock_code": code,
                        "stock_name": name,
                        "strength": 2.0,
                        "reasons": [
                            f"首封 {first_time}",
                            f"封板资金 {seal_money/1e8:.1f}亿" if seal_money else "",
                            f"连板 {chain_count}" if chain_count else "",
                        ],
                        "raw_data": {
                            "seal_money": seal_money,
                            "first_time": str(first_time),
                            "chain_count": str(chain_count),
                        }
                    })
                    # 清理空原因
                    signals[-1]["reasons"] = [r for r in signals[-1]["reasons"] if r]
            
            self._known_zt_stocks = current_codes
        
        # 炸板检测（带去重：同一只票的炸板信号在已知集合内不重复生成）
        if current_zb is not None and not current_zb.empty and "代码" in current_zb.columns:
            current_zb_codes = set(current_zb["代码"].tolist())
            new_zb = current_zb_codes - self._known_zb_stocks
            
            for code in new_zb:
                zb_row = current_zb[current_zb["代码"] == code]
                if zb_row.empty:
                    continue
                row = zb_row.iloc[0]
                name = row.get("名称", "未知")
                open_count = row.get("炸板次数", 0) or 0
                
                signals.append({
                    "signal_type": "涨停炸板",
                    "stock_code": code,
                    "stock_name": name,
                    "strength": 1.5,
                    "reasons": [f"炸板 {open_count} 次" if open_count else "涨停打开"],
                    "raw_data": {
                        "open_count": open_count,
                    }
                })
            
            self._known_zb_stocks = current_zb_codes
        
        return signals
