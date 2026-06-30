"""
PulseRadar — 入口脚本
支持命令行控制：start / stop / status / today / watch / unwatch / watchlist
"""

import argparse
import json
import os
import sys
import signal
import logging
from datetime import datetime
from pathlib import Path

# 将 src 的父目录加入 path，确保模块可以正确导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scanner import PulseRadarScanner
from src.logger import SignalLogger
from src.watchlist import WatchlistManager
from src.config_validator import validate_config, sanitize_config


def get_config_path(args_config: str | None = None) -> str:
    """获取配置文件路径。"""
    if args_config:
        return args_config
    return str(Path(__file__).resolve().parent.parent / "config.json")


def load_config(config_path: str | None = None) -> dict:
    """加载配置文件，自动校验并补全缺省值。"""
    if config_path is None:
        config_path = get_config_path()
    
    raw_config: dict = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)
    
    # 校验：仅对已提供的字段做合法性检查
    is_valid, errors = validate_config(raw_config)
    if not is_valid:
        logger = logging.getLogger("PulseRadar")
        logger.warning("配置校验发现 %d 个问题:", len(errors))
        for err in errors:
            logger.warning("  - %s", err)
        logger.warning("已自动使用默认值补全，建议检查 config.json")
    
    # 补全缺省值
    config = sanitize_config(raw_config)
    
    # 保留用户可能额外添加的顶层字段（如 trading_hours、enabled 等）
    for key, value in raw_config.items():
        if key not in config:
            config[key] = value
    
    return config


def setup_logging(output_dir: str, verbose: bool = False):
    """配置日志（带轮转：单文件 5MB，保留 3 份历史）。"""
    from logging.handlers import RotatingFileHandler

    log_dir = Path(os.path.expanduser(output_dir))
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_level = logging.DEBUG if verbose else logging.INFO
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 文件日志：5 MB 轮转，保留 3 份
    file_handler = RotatingFileHandler(
        log_dir / "pulse-radar.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    # 控制台日志
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)

    logging.basicConfig(
        level=log_level,
        handlers=[stream_handler, file_handler],
    )


def get_pid_and_status(config: dict) -> tuple[int | None, dict | None]:
    """获取正在运行的 PulseRadar 的 PID 和状态。"""
    output_dir = Path(os.path.expanduser(config.get("output_dir", "~/Desktop/PulseRadar")))
    
    pid = None
    pid_file = output_dir / "pulse-radar.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            # 检查进程是否还活着
            os.kill(pid, 0)
        except (ValueError, ProcessLookupError, PermissionError):
            pid = None
            pid_file.unlink(missing_ok=True)
    
    status = None
    status_file = output_dir / "status.json"
    if status_file.exists():
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                status = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    
    return pid, status


def cmd_start(args, config: dict):
    """启动 PulseRadar 后台扫描。"""
    # 检查是否已在运行
    pid, _ = get_pid_and_status(config)
    if pid is not None:
        print(f"PulseRadar 已在运行中 (PID: {pid})")
        sys.exit(1)
    
    setup_logging(config.get("output_dir", "~/Desktop/PulseRadar"), args.verbose)
    
    config_path = get_config_path(args.config if hasattr(args, 'config') else None)
    scanner = PulseRadarScanner(config, config_path=config_path)
    
    if args.foreground:
        # 前台运行（调试用）
        print("PulseRadar 前台启动中... (Ctrl+C 停止)")
        scanner.run()
    else:
        # 后台运行
        print("PulseRadar 正在启动...")
        scanner.run()


def cmd_stop(args, config: dict):
    """停止 PulseRadar。"""
    pid, _ = get_pid_and_status(config)
    if pid is None:
        print("PulseRadar 未在运行")
        return
    
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"已向 PulseRadar (PID: {pid}) 发送停止信号")
    except ProcessLookupError:
        print("PulseRadar 进程已不存在")
        # 清理 PID 文件
        output_dir = Path(os.path.expanduser(config.get("output_dir", "~/Desktop/PulseRadar")))
        (output_dir / "pulse-radar.pid").unlink(missing_ok=True)


def cmd_status(args, config: dict):
    """查看 PulseRadar 运行状态。"""
    pid, status = get_pid_and_status(config)
    
    if pid is None:
        print("PulseRadar 当前未运行")
        if status:
            print(f"上次运行时间: {status.get('start_time', '未知')}")
        return
    
    print(f"PulseRadar 运行中 (PID: {pid})")
    if status:
        start_time = status.get("start_time", "未知")
        scan_count = status.get("scan_count", 0)
        signal_count = status.get("signal_count", 0)
        notify_count = status.get("notify_count", 0)
        last_scan = status.get("last_scan_time", "未知")
        stock_count = status.get("last_stock_count", 0)
        errors = status.get("errors", 0)
        
        print(f"  启动时间: {start_time}")
        print(f"  扫描次数: {scan_count}")
        print(f"  最近扫描: {last_scan} ({stock_count} 只)")
        print(f"  异动信号: {signal_count} 个")
        print(f"  已推送: {notify_count} 条通知")
        if errors:
            print(f"  错误次数: {errors}")
    
    # 显示自选股状态
    config_path = get_config_path(getattr(args, '_config_path', None))
    wm = WatchlistManager(config_path)
    if wm.enabled and wm.stocks:
        print(f"\n  自选股盯梢: 已启用 ({len(wm.stocks)} 只)")
        print(f"  自选股推送阈值: {wm.push_threshold} 分")


def cmd_today(args, config: dict):
    """查看今日异动汇总。"""
    output_dir = config.get("output_dir", "~/Desktop/PulseRadar")
    signal_logger = SignalLogger(output_dir)
    summary = signal_logger.get_today_summary()
    
    print(f"\n📊 PulseRadar 今日异动汇总 ({summary['date']})")
    print("=" * 50)
    
    if summary["total_signals"] == 0:
        print("今日暂无异动信号")
        return
    
    print(f"总计 {summary['total_signals']} 个信号，已推送 {summary.get('notified_count', 0)} 条通知")
    
    # 按类型统计
    by_type = summary.get("by_type", {})
    if by_type:
        print("\n按类型:")
        for sig_type, count in by_type.items():
            print(f"  {sig_type}: {count} 个")
    
    # Top 10
    top = summary.get("top_10", [])
    if top:
        print("\nTop 10 异动:")
        for i, item in enumerate(top, 1):
            print(
                f"  {i}. {item['stock']} | "
                f"评分 {item['score']:.0f} | "
                f"{item['type']} | "
                f"{item['time']}"
            )


def cmd_watch(args, config: dict):
    """添加自选股。"""
    config_path = get_config_path(getattr(args, '_config_path', None))
    wm = WatchlistManager(config_path)
    
    code = args.code
    name = args.name or code  # 如果没提供名称，先用代码占位
    stop_loss = args.stop_loss
    target_price = args.target_price
    
    if wm.add_stock(code, name, stop_loss=stop_loss, target_price=target_price):
        msg = f"已添加自选股: {name} ({code})"
        if target_price:
            msg += f" | 目标价 {target_price:.2f}"
        if stop_loss:
            msg += f" | 止损价 {stop_loss:.2f}"
        print(msg)
    else:
        print(f"自选股 {code} 已存在")


def cmd_unwatch(args, config: dict):
    """移除自选股。"""
    config_path = get_config_path(getattr(args, '_config_path', None))
    wm = WatchlistManager(config_path)
    
    removed_name = wm.remove_stock(args.code)
    if removed_name:
        print(f"已移除自选股: {removed_name} ({args.code})")
    else:
        print(f"自选股中未找到 {args.code}")


def cmd_watchlist(args, config: dict):
    """查看自选股列表。"""
    config_path = get_config_path(getattr(args, '_config_path', None))
    wm = WatchlistManager(config_path)
    
    stocks = wm.list_stocks()
    if not stocks:
        print("自选股列表为空")
        print("使用 'watch <代码> --name <名称>' 添加自选股")
        return
    
    enabled_str = "已启用" if wm.enabled else "已禁用"
    print(f"\n⭐ 自选股列表 ({len(stocks)} 只 · {enabled_str} · 推送阈值 {wm.push_threshold} 分)")
    print("-" * 50)
    
    for s in stocks:
        line = f"  {s['name']} ({s['code']})"
        extras = []
        if s.get("target_price"):
            extras.append(f"目标价 {s['target_price']:.2f}")
        if s.get("stop_loss"):
            extras.append(f"止损价 {s['stop_loss']:.2f}")
        if extras:
            line += f" | {' | '.join(extras)}"
        print(line)


def main():
    parser = argparse.ArgumentParser(
        description="PulseRadar — AI 盘中异动雷达",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", "-c",
        help="配置文件路径 (默认: config.json)",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # start 命令
    start_parser = subparsers.add_parser("start", help="启动盯盘")
    start_parser.add_argument("--foreground", "-f", action="store_true", help="前台运行（调试用）")
    start_parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
    
    # stop 命令
    subparsers.add_parser("stop", help="停止盯盘")
    
    # status 命令
    subparsers.add_parser("status", help="查看运行状态")
    
    # today 命令
    subparsers.add_parser("today", help="查看今日异动汇总")
    
    # watch 命令（添加自选股）
    watch_parser = subparsers.add_parser("watch", help="添加自选股")
    watch_parser.add_argument("code", help="股票代码 (如 603986)")
    watch_parser.add_argument("--name", "-n", help="股票名称 (如 兆易创新)")
    watch_parser.add_argument("--stop-loss", "-sl", type=float, help="止损价")
    watch_parser.add_argument("--target-price", "-tp", type=float, help="目标价")
    
    # unwatch 命令（移除自选股）
    unwatch_parser = subparsers.add_parser("unwatch", help="移除自选股")
    unwatch_parser.add_argument("code", help="股票代码 (如 603986)")
    
    # watchlist 命令（查看自选股列表）
    subparsers.add_parser("watchlist", help="查看自选股列表")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    config_path = get_config_path(args.config)
    config = load_config(config_path)
    
    # 将 config_path 挂到 args 上供子命令使用
    args._config_path = config_path
    
    commands = {
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "today": cmd_today,
        "watch": cmd_watch,
        "unwatch": cmd_unwatch,
        "watchlist": cmd_watchlist,
    }
    
    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args, config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
