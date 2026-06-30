"""
PulseRadar — JSON 日志系统
记录每次异动信号，支持按日查询和复盘。
"""

import json
import os
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class SignalLogger:
    """异动信号 JSON 日志记录器（自动清理超过 retention_days 的旧日志）。"""
    
    def __init__(self, output_dir: str, retention_days: int = 30):
        self.output_dir = Path(os.path.expanduser(output_dir))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self._today_file: Path | None = None
        self._today_date: str = ""
        self._signals_today: list[dict] = []
        self._last_cleanup_date: str = ""
    
    def _get_log_file(self, date: str | None = None) -> Path:
        """获取指定日期的日志文件路径。"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        return self.output_dir / f"pulse-radar-{date}.json"
    
    def _ensure_today_file(self):
        """确保当日日志文件已加载。"""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._today_date:
            # 日期切换，重新加载
            self._today_date = today
            self._today_file = self._get_log_file(today)
            if self._today_file.exists():
                try:
                    with open(self._today_file, "r", encoding="utf-8") as f:
                        self._signals_today = json.load(f)
                except (json.JSONDecodeError, IOError):
                    self._signals_today = []
            else:
                self._signals_today = []
    
    def log_signal(self, signal: dict):
        """
        记录一条异动信号。
        
        参数:
            signal: 异动信号字典，包含:
                - timestamp: ISO 格式时间戳
                - stock_code: 股票代码
                - stock_name: 股票名称
                - signal_type: 信号类型
                - score: 异动评分
                - price: 当时价格
                - change_pct: 涨跌幅
                - volume_ratio: 量比
                - reasons: 触发原因列表
                - notified: 是否已推送通知
        """
        self._ensure_today_file()
        
        # 添加时间戳（如果没有）
        if "timestamp" not in signal:
            signal["timestamp"] = datetime.now().isoformat()
        
        self._signals_today.append(signal)
        
        # 写入文件
        try:
            with open(self._today_file, "w", encoding="utf-8") as f:
                json.dump(self._signals_today, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"写入日志文件失败: {e}")
    
    def get_today_signals(self) -> list[dict]:
        """获取今天的所有异动记录。"""
        self._ensure_today_file()
        return self._signals_today.copy()
    
    def get_today_summary(self) -> dict:
        """获取今日异动汇总摘要。"""
        signals = self.get_today_signals()
        
        if not signals:
            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "total_signals": 0,
                "summary": "今日暂无异动信号"
            }
        
        # 按信号类型统计
        type_counts: dict[str, int] = {}
        notified_count = 0
        top_scores: list[dict] = []
        
        for s in signals:
            sig_type = s.get("signal_type", "未知")
            type_counts[sig_type] = type_counts.get(sig_type, 0) + 1
            if s.get("notified"):
                notified_count += 1
            top_scores.append({
                "stock": f"{s.get('stock_name', '?')} ({s.get('stock_code', '?')})",
                "score": s.get("score", 0),
                "type": sig_type,
                "time": s.get("timestamp", "")[:19],
            })
        
        # 按评分排序取 top 10
        top_scores.sort(key=lambda x: x["score"], reverse=True)
        
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_signals": len(signals),
            "notified_count": notified_count,
            "by_type": type_counts,
            "top_10": top_scores[:10],
        }
    
    def get_signals_by_date(self, date: str) -> list[dict]:
        """获取指定日期的异动记录。"""
        log_file = self._get_log_file(date)
        if not log_file.exists():
            return []
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def cleanup_old_logs(self):
        """删除超过 retention_days 天的旧 JSON 信号日志。每天最多执行一次。"""
        from datetime import timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        if today == self._last_cleanup_date:
            return  # 今天已执行过
        self._last_cleanup_date = today

        cutoff = datetime.now() - timedelta(days=self.retention_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        removed = 0
        for f in self.output_dir.glob("pulse-radar-*.json"):
            # 文件名格式: pulse-radar-YYYY-MM-DD.json
            try:
                date_part = f.stem.replace("pulse-radar-", "")
                if date_part < cutoff_str:
                    f.unlink()
                    removed += 1
            except (ValueError, OSError) as e:
                logger.warning("清理旧日志 %s 失败: %s", f.name, e)
        if removed:
            logger.info("已清理 %d 个超过 %d 天的旧日志文件", removed, self.retention_days)
