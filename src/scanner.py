"""
PulseRadar — 自选股行情播报引擎
仅拉取自选股实时数据，定时播报行情和异动信号。
交易时间内轮询，收盘后自动停止。
"""

import json
import os
import sys
import time
import signal as os_signal
import logging
import re as _re
import random
from datetime import datetime
from pathlib import Path

import requests as _requests
import pandas as pd

from .signals import SignalDetector
from .scoring import score_signals, merge_signals
from .notifier import notify_signal, send_desktop_notification
from .logger import SignalLogger
from .watchlist import WatchlistManager, WatchlistGuard
from .watchlist_report import generate_watchlist_report, push_watchlist_report
from .holidays import is_trading_day

logger = logging.getLogger(__name__)

# 随机 User-Agent 池
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


class PulseRadarScanner:
    """PulseRadar 自选股行情播报引擎。"""

    def __init__(self, config: dict, config_path: str | None = None):
        self.config = config
        self.config_path = config_path
        self.running = False

        # 轮询间隔（秒），即两次拉取之间的最小间隔
        self.poll_interval = config.get("poll_interval", 60)
        self.push_threshold = config.get("push_threshold", 60)

        # 收盘后自动停止（默认开启）
        self.auto_stop_after_close = config.get("auto_stop_after_close", True)
        # 已发送收盘通知标记
        self._close_notified = False

        # 输出目录（相对路径基于项目根目录解析）
        output_dir = config.get("output_dir", "./output")
        output_path = Path(os.path.expanduser(output_dir))
        if not output_path.is_absolute() and config_path:
            output_path = Path(config_path).parent / output_path
        self.output_dir = output_path.resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # PID 文件 & 状态文件
        self.pid_file = self.output_dir / "pulse-radar.pid"
        self.status_file = self.output_dir / "status.json"

        # 组件
        self.signal_detector = SignalDetector(config)
        self.signal_logger = SignalLogger(str(self.output_dir))

        # 自选股
        self.watchlist_mgr = WatchlistManager(config_path)
        self.watchlist_guard = WatchlistGuard(
            self.watchlist_mgr, self.signal_detector, config
        )

        # 日期追踪
        self._current_date = datetime.now().strftime("%Y-%m-%d")

        # 统计
        self.stats = {
            "start_time": None,
            "scan_count": 0,
            "signal_count": 0,
            "notify_count": 0,
            "last_scan_time": None,
            "last_stock_count": 0,
            "errors": 0,
        }

        # 播报间隔
        self._last_watchlist_report_time: float = 0
        self._watchlist_report_interval: int = config.get("watchlist_report_interval", 60)

        # 退避
        self._consecutive_failures = 0
        self._max_backoff = 300
        self._base_backoff = 30
        self._backoff_until: float = 0

        # 价格快照缓存（涨速 / 5分钟涨跌）
        self._price_snapshots: dict[str, list[tuple[float, float]]] = {}
        self._snapshot_max_age = 600

    # ─── 交易时间 ───

    def is_trading_hours(self) -> bool:
        """检查当前是否在交易时间内。"""
        now = datetime.now()
        if not is_trading_day(now.date()):
            return False

        hours = self.config.get("trading_hours", {})
        current_time = now.strftime("%H:%M")

        morning_start = hours.get("morning_start", "09:25")
        morning_end = hours.get("morning_end", "11:30")
        afternoon_start = hours.get("afternoon_start", "13:00")
        afternoon_end = hours.get("afternoon_end", "15:05")

        return (morning_start <= current_time <= morning_end
                or afternoon_start <= current_time <= afternoon_end)

    def _is_after_close(self) -> bool:
        """判断当前是否已过收盘时间（15:05 之后）。"""
        now = datetime.now()
        if not is_trading_day(now.date()):
            return False  # 非交易日不算"收盘后"
        close_time = self.config.get("trading_hours", {}).get("afternoon_end", "15:05")
        return now.strftime("%H:%M") > close_time

    # ─── 退避 ───

    def _calculate_backoff(self) -> float:
        if self._consecutive_failures <= 0:
            return 0
        backoff = min(
            self._base_backoff * (2 ** (self._consecutive_failures - 1)),
            self._max_backoff,
        )
        jitter = backoff * 0.2 * (random.random() * 2 - 1)
        return max(backoff + jitter, 10)

    def _on_fetch_success(self):
        if self._consecutive_failures > 0:
            logger.info(f"API 恢复正常（之前连续失败 {self._consecutive_failures} 次）")
        self._consecutive_failures = 0

    def _on_fetch_failure(self, error_msg: str):
        self._consecutive_failures += 1
        backoff = self._calculate_backoff()
        self._backoff_until = time.time() + backoff
        logger.warning(
            f"请求失败（连续第 {self._consecutive_failures} 次）: {error_msg}  "
            f"→ 退避 {backoff:.0f} 秒后重试"
        )

    # ─── 数据拉取：仅自选股 ───

    def _get_watchlist_tencent_codes(self) -> list[str]:
        """将自选股代码转为腾讯 API 格式（sh/sz 前缀）。"""
        codes = []
        for stock in self.watchlist_mgr.stocks:
            code = stock["code"]
            if code.startswith("6") or code.startswith("9") or code.startswith("68"):
                codes.append(f"sh{code}")
            else:
                codes.append(f"sz{code}")
        return codes

    def _fetch_watchlist_data(self) -> pd.DataFrame | None:
        """
        使用腾讯财经 API 仅拉取自选股实时行情。
        自选股数量少（通常 <20 只），单次请求即可完成，对 API 压力极小。
        """
        codes = self._get_watchlist_tencent_codes()
        if not codes:
            logger.debug("自选股列表为空，跳过拉取")
            return None

        # 退避检查
        if time.time() < self._backoff_until:
            remaining = int(self._backoff_until - time.time())
            logger.warning(f"退避中，剩余 {remaining} 秒")
            return None

        url = f"https://qt.gtimg.cn/q={','.join(codes)}"
        headers = {"User-Agent": random.choice(_USER_AGENTS)}

        try:
            resp = _requests.get(url, headers=headers, timeout=15)
            resp.encoding = "gbk"
        except Exception as e:
            self._on_fetch_failure(str(e))
            self.stats["errors"] += 1
            return None

        all_data = []
        for line in resp.text.strip().split(";"):
            line = line.strip()
            if not line or '=""' in line:
                continue
            match = _re.search(r'v_(\w+)="(.+)"', line)
            if not match:
                continue
            fields = match.group(2).split("~")
            if len(fields) < 49:
                continue
            try:
                price = float(fields[3]) if fields[3] else None
                if price is None or price <= 0:
                    continue

                turnover_wan = float(fields[37]) if fields[37] else 0
                flow_cap_yi = float(fields[44]) if fields[44] else 0
                total_cap_yi = float(fields[45]) if fields[45] else 0

                all_data.append({
                    "代码": fields[2],
                    "名称": fields[1],
                    "最新价": price,
                    "涨跌幅": float(fields[32]) if fields[32] else 0,
                    "涨跌额": float(fields[31]) if fields[31] else 0,
                    "成交量": int(float(fields[36])) if fields[36] else 0,
                    "成交额": turnover_wan * 10000,
                    "振幅": float(fields[43]) if fields[43] else 0,
                    "最高": float(fields[33]) if fields[33] else 0,
                    "最低": float(fields[34]) if fields[34] else 0,
                    "今开": float(fields[5]) if fields[5] else 0,
                    "昨收": float(fields[4]) if fields[4] else 0,
                    "换手率": float(fields[38]) if fields[38] else 0,
                    "市盈率-动态": float(fields[39]) if fields[39] else 0,
                    "流通市值": flow_cap_yi * 1e8,
                    "总市值": total_cap_yi * 1e8,
                    "市净率": float(fields[46]) if fields[46] else 0,
                    "量比": float(fields[49]) if len(fields) > 49 and fields[49] else 0,
                })
            except (ValueError, IndexError):
                continue

        if not all_data:
            self._on_fetch_failure("腾讯 API 未返回有效数据")
            self.stats["errors"] += 1
            return None

        self._on_fetch_success()

        df = pd.DataFrame(all_data)
        df.insert(0, "序号", range(1, len(df) + 1))

        # 数值转换
        for col in ["最新价", "涨跌幅", "涨跌额", "成交量", "成交额", "振幅",
                     "最高", "最低", "今开", "昨收", "换手率", "市盈率-动态",
                     "市净率", "总市值", "流通市值"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 计算涨速、5分钟涨跌
        df = self._enrich_speed_fields(df)

        self.stats["last_stock_count"] = len(df)
        logger.info(f"获取到 {len(df)} 只自选股数据")
        return df

    # ─── 涨速 / 5分钟涨跌 ───

    def _enrich_speed_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        """基于快照缓存计算涨速和5分钟涨跌。"""
        now = time.time()

        # 清理过期
        expired = [c for c, snaps in self._price_snapshots.items()
                   if not any(now - ts < self._snapshot_max_age for ts, _ in snaps)]
        for c in expired:
            del self._price_snapshots[c]
        for c in self._price_snapshots:
            self._price_snapshots[c] = [
                (ts, p) for ts, p in self._price_snapshots[c]
                if now - ts < self._snapshot_max_age
            ]

        speed_values, five_min_values = [], []

        for _, row in df.iterrows():
            code = row.get("代码", "")
            price = row.get("最新价", 0)

            if not code or not price or price <= 0:
                speed_values.append(0)
                five_min_values.append(0)
                continue

            self._price_snapshots.setdefault(code, []).append((now, price))

            # 涨速: ~1 分钟前
            speed = 0
            for ts, p in reversed(self._price_snapshots[code]):
                age = now - ts
                if 30 <= age <= 120 and p > 0:
                    speed = (price - p) / p * 100 / (age / 60)
                    break

            # 5分钟涨跌: ~5 分钟前
            five_min = 0
            for ts, p in reversed(self._price_snapshots[code]):
                age = now - ts
                if 240 <= age <= 420 and p > 0:
                    five_min = (price - p) / p * 100
                    break

            speed_values.append(round(speed, 2))
            five_min_values.append(round(five_min, 2))

        df["涨速"] = speed_values
        df["5分钟涨跌"] = five_min_values
        return df

    # ─── 扫描逻辑 ───

    def scan_once(self) -> list[dict]:
        """执行一次扫描：拉取自选股数据 → 信号检测 → 行情播报。"""
        self.stats["scan_count"] += 1
        self.stats["last_scan_time"] = datetime.now().isoformat()

        df = self._fetch_watchlist_data()
        if df is None:
            return []

        triggered_signals = []

        # 1. 自选股信号检测
        watchlist_signals = self.watchlist_guard.scan_watchlist(df)
        if watchlist_signals:
            logger.info(f"自选股触发 {len(watchlist_signals)} 个信号")
            triggered_signals.extend(watchlist_signals)

        # 2. 行情播报（按 watchlist_report_interval 间隔）
        now_ts = time.time()
        if now_ts - self._last_watchlist_report_time >= self._watchlist_report_interval:
            watch_codes = self.watchlist_mgr.get_stock_codes()
            if watch_codes:
                try:
                    reports = generate_watchlist_report(df, watch_codes)
                    if reports:
                        push_watchlist_report(reports)
                        self._last_watchlist_report_time = now_ts
                        summaries = []
                        for r in reports:
                            sign = "+" if r["change_pct"] > 0 else ""
                            summaries.append(f"{r['name']} {sign}{r['change_pct']:.2f}%")
                        logger.info(f"自选股播报: {', '.join(summaries)}")
                except Exception as e:
                    logger.warning(f"自选股播报失败: {e}")

        self.stats["signal_count"] += len(triggered_signals)
        return triggered_signals

    def process_signals(self, signals: list[dict]):
        """处理异动信号：记录日志 + 推送通知。"""
        for signal in signals:
            self.signal_logger.log_signal(signal)
            notified = notify_signal(signal, self.config)
            if notified:
                signal["notified"] = True
                self.stats["notify_count"] += 1

    # ─── 状态管理 ───

    def save_status(self):
        status = {"running": self.running, "pid": os.getpid(), **self.stats}
        try:
            with open(self.status_file, "w", encoding="utf-8") as f:
                json.dump(status, f, ensure_ascii=False, indent=2)
        except IOError:
            pass

    def write_pid(self):
        with open(self.pid_file, "w") as f:
            f.write(str(os.getpid()))

    def remove_pid(self):
        try:
            self.pid_file.unlink(missing_ok=True)
        except OSError:
            pass

    def stop(self):
        logger.info("正在停止 PulseRadar...")
        self.running = False

    # ─── 主循环 ───

    def run(self):
        """启动扫描主循环。"""
        self.running = True
        self.stats["start_time"] = datetime.now().isoformat()
        self.write_pid()

        def handle_signal(signum, frame):
            self.stop()

        os_signal.signal(os_signal.SIGTERM, handle_signal)
        os_signal.signal(os_signal.SIGINT, handle_signal)

        watch_count = len(self.watchlist_mgr.stocks)
        logger.info(
            f"PulseRadar 已启动 (PID: {os.getpid()}, "
            f"自选股: {watch_count} 只, "
            f"轮询间隔: {self.poll_interval}s)"
        )

        send_desktop_notification(
            "PulseRadar 已启动",
            f"盯梢 {watch_count} 只自选股 | 轮询间隔 {self.poll_interval}s",
            "info",
        )

        try:
            while self.running:
                # 收盘后自动停止
                if self.auto_stop_after_close and self._is_after_close():
                    if not self._close_notified:
                        logger.info("已过收盘时间，自动停止")
                        send_desktop_notification(
                            "PulseRadar 已收盘停止",
                            f"今日扫描 {self.stats['scan_count']} 次，"
                            f"发现 {self.stats['signal_count']} 个信号",
                            "info",
                        )
                        self._close_notified = True
                    break

                # 非交易时间等待
                if not self.is_trading_hours():
                    logger.debug("非交易时间，等待中...")
                    self.save_status()
                    time.sleep(30)
                    continue

                # 每日重置
                today = datetime.now().strftime("%Y-%m-%d")
                if today != self._current_date:
                    self._current_date = today
                    self._close_notified = False
                    self.watchlist_guard.reset_daily_state()
                    self.signal_logger.cleanup_old_logs()
                    self._price_snapshots.clear()
                    logger.info(f"新交易日 {today}，状态已重置")

                # 扫描
                scan_start = time.time()
                try:
                    signals = self.scan_once()
                    if signals:
                        logger.info(f"发现 {len(signals)} 个信号")
                        self.process_signals(signals)
                except Exception as e:
                    logger.error(f"扫描异常: {e}", exc_info=True)
                    self.stats["errors"] += 1

                scan_elapsed = time.time() - scan_start
                logger.info(f"本轮扫描耗时 {scan_elapsed:.1f}s")
                self.save_status()

                # 等待：退避 or 正常间隔
                if self._consecutive_failures > 0 and self._backoff_until > time.time():
                    wait_time = self._backoff_until - time.time()
                    logger.info(f"退避等待 {wait_time:.0f}s")
                else:
                    wait_time = max(self.poll_interval - scan_elapsed, 1)

                if wait_time > 0:
                    time.sleep(wait_time)

        finally:
            self.running = False
            self.save_status()
            self.remove_pid()
            logger.info("PulseRadar 已停止")
