"""
PulseRadar — 自选股盯梢模块 (Watchlist Guard)
管理自选股列表，提供低阈值异动检测、关键价位提醒、止损预警。
自选股不受全市场过滤器限制。
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class WatchlistManager:
    """自选股列表管理器。"""
    
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self._config: dict = {}
        self._load_config()
    
    def _load_config(self):
        """加载配置文件。"""
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
    
    def _save_config(self):
        """保存配置文件。"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._config, f, ensure_ascii=False, indent=2)
            f.write("\n")
    
    @property
    def watchlist_config(self) -> dict:
        return self._config.get("watchlist", {})
    
    @property
    def enabled(self) -> bool:
        return self.watchlist_config.get("enabled", False)
    
    @property
    def stocks(self) -> list[dict]:
        return self.watchlist_config.get("stocks", [])
    
    @property
    def push_threshold(self) -> int:
        return self.watchlist_config.get("push_threshold", 30)
    
    def add_stock(self, code: str, name: str, 
                  stop_loss: float | None = None,
                  target_price: float | None = None) -> bool:
        """
        添加自选股。
        
        参数:
            code: 股票代码（如 "603986"）
            name: 股票名称（如 "兆易创新"）
            stop_loss: 止损价（可选）
            target_price: 目标价（可选）
        
        返回:
            是否添加成功（已存在返回 False）
        """
        watchlist = self._config.setdefault("watchlist", {
            "enabled": True, "stocks": [], "push_threshold": 30, "midday_summary": True
        })
        stocks = watchlist.setdefault("stocks", [])
        
        # 检查是否已存在
        for s in stocks:
            if s["code"] == code:
                return False
        
        stocks.append({
            "code": code,
            "name": name,
            "stop_loss": stop_loss,
            "target_price": target_price,
        })
        
        # 添加后自动启用
        watchlist["enabled"] = True
        self._save_config()
        logger.info(f"已添加自选股: {name} ({code})")
        return True
    
    def remove_stock(self, code: str) -> str | None:
        """
        移除自选股。
        
        返回:
            被移除的股票名称，不存在则返回 None
        """
        stocks = self._config.get("watchlist", {}).get("stocks", [])
        for i, s in enumerate(stocks):
            if s["code"] == code:
                removed = stocks.pop(i)
                self._save_config()
                logger.info(f"已移除自选股: {removed['name']} ({code})")
                return removed["name"]
        return None
    
    def list_stocks(self) -> list[dict]:
        """返回自选股列表。"""
        return self.stocks.copy()
    
    def get_stock_codes(self) -> set[str]:
        """返回自选股代码集合。"""
        return {s["code"] for s in self.stocks}
    
    def get_stock_config(self, code: str) -> dict | None:
        """获取某只自选股的配置（含止损/目标价）。"""
        for s in self.stocks:
            if s["code"] == code:
                return s
        return None


class WatchlistGuard:
    """
    自选股盯梢逻辑。
    与全市场扫描并行运行，提供：
    - 低阈值异动检测（默认 30 分）
    - 关键价位提醒（目标价/止损价）
    - 午盘状态小结
    """
    
    def __init__(self, watchlist_mgr: WatchlistManager, signal_detector, config: dict):
        self.watchlist_mgr = watchlist_mgr
        self.signal_detector = signal_detector
        self.config = config
        
        # 价位提醒去重：{code: set_of_triggered_types}
        # 类型: "target_reached", "stop_loss_hit"
        self._price_alert_triggered: dict[str, set[str]] = {}
        
        # 午盘小结标记
        self._midday_summary_sent = False
    
    def scan_watchlist(self, market_df: pd.DataFrame) -> list[dict]:
        """
        对自选股执行盯梢检测。
        
        参数:
            market_df: 全市场行情 DataFrame（未过滤的原始数据）
        
        返回:
            触发的信号列表（含低阈值异动 + 价位提醒）
        """
        if not self.watchlist_mgr.enabled:
            return []
        
        watch_codes = self.watchlist_mgr.get_stock_codes()
        if not watch_codes:
            return []
        
        # 从全市场数据中筛选自选股（不经过过滤器）
        if "代码" not in market_df.columns:
            return []
        
        watch_df = market_df[market_df["代码"].isin(watch_codes)]
        if watch_df.empty:
            return []
        
        from .scoring import score_signals, merge_signals
        
        triggered = []
        push_threshold = self.watchlist_mgr.push_threshold
        
        for _, row in watch_df.iterrows():
            stock_code = row.get("代码", "")
            stock_data = row.to_dict()
            
            # 1. 信号检测（与全市场相同的检测逻辑）
            signals = self.signal_detector.detect_all(row)
            if signals:
                score = score_signals(signals, stock_data)
                if score >= push_threshold:
                    record = merge_signals(signals, stock_data, score)
                    record["is_watchlist"] = True
                    triggered.append(record)
            
            # 2. 价位提醒
            price_alerts = self._check_price_alerts(stock_code, stock_data)
            triggered.extend(price_alerts)
        
        return triggered
    
    def _check_price_alerts(self, code: str, stock_data: dict) -> list[dict]:
        """检查自选股的价位提醒（目标价/止损价）。"""
        stock_config = self.watchlist_mgr.get_stock_config(code)
        if not stock_config:
            return []
        
        alerts = []
        current_price = stock_data.get("最新价", 0) or 0
        if current_price <= 0:
            return []
        
        triggered_set = self._price_alert_triggered.setdefault(code, set())
        stock_name = stock_data.get("名称", stock_config.get("name", "未知"))
        
        # 目标价提醒
        target_price = stock_config.get("target_price")
        if target_price and current_price >= target_price and "target_reached" not in triggered_set:
            triggered_set.add("target_reached")
            alerts.append({
                "stock_code": code,
                "stock_name": stock_name,
                "signal_type": "目标价到达",
                "score": 90,
                "price": current_price,
                "change_pct": stock_data.get("涨跌幅", 0),
                "volume_ratio": stock_data.get("量比", 0),
                "reasons": [f"当前价 {current_price:.2f} 已达目标价 {target_price:.2f}"],
                "timestamp": datetime.now().isoformat(),
                "notified": False,
                "is_watchlist": True,
            })
        
        # 止损预警
        stop_loss = stock_config.get("stop_loss")
        if stop_loss and current_price <= stop_loss and "stop_loss_hit" not in triggered_set:
            triggered_set.add("stop_loss_hit")
            alerts.append({
                "stock_code": code,
                "stock_name": stock_name,
                "signal_type": "止损预警",
                "score": 95,
                "price": current_price,
                "change_pct": stock_data.get("涨跌幅", 0),
                "volume_ratio": stock_data.get("量比", 0),
                "reasons": [f"当前价 {current_price:.2f} 已跌破止损线 {stop_loss:.2f}"],
                "timestamp": datetime.now().isoformat(),
                "notified": False,
                "is_watchlist": True,
            })
        
        return alerts
    
    def generate_midday_summary(self, market_df: pd.DataFrame) -> dict | None:
        """
        生成午盘自选股状态小结。
        在 11:30-13:00 期间调用，且每天只生成一次。
        
        返回:
            小结数据字典，或 None（已发送/未启用/无自选股）
        """
        if self._midday_summary_sent:
            return None
        
        if not self.watchlist_mgr.enabled:
            return None
        
        if not self.watchlist_mgr.watchlist_config.get("midday_summary", True):
            return None
        
        watch_codes = self.watchlist_mgr.get_stock_codes()
        if not watch_codes or "代码" not in market_df.columns:
            return None
        
        watch_df = market_df[market_df["代码"].isin(watch_codes)]
        if watch_df.empty:
            return None
        
        self._midday_summary_sent = True
        
        stock_summaries = []
        for _, row in watch_df.iterrows():
            code = row.get("代码", "")
            name = row.get("名称", "")
            price = row.get("最新价", 0)
            change_pct = row.get("涨跌幅", 0)
            volume_ratio = row.get("量比", 0)
            turnover = row.get("成交额", 0)
            
            sign = "+" if change_pct > 0 else ""
            turnover_str = f"{turnover/1e8:.1f}亿" if turnover >= 1e8 else f"{turnover/1e4:.0f}万"
            
            stock_summaries.append({
                "code": code,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "volume_ratio": volume_ratio,
                "summary_line": f"{name} {sign}{change_pct:.1f}% 现价{price:.2f} 成交{turnover_str}",
            })
        
        # 按涨跌幅排序
        stock_summaries.sort(key=lambda x: x["change_pct"], reverse=True)
        
        return {
            "type": "midday_summary",
            "timestamp": datetime.now().isoformat(),
            "stock_count": len(stock_summaries),
            "stocks": stock_summaries,
        }
    
    def reset_daily_state(self):
        """每日重置状态（新交易日开始时调用）。"""
        self._price_alert_triggered.clear()
        self._midday_summary_sent = False
