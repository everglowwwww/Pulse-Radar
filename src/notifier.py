"""
PulseRadar — 通知推送模块
支持桌面通知（catdesk notify）、大象消息、通知声音。含去重机制。
"""

import subprocess
import time
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 通知去重缓存: {stock_code: last_notify_timestamp}
_notify_cache: dict[str, float] = {}
# 同一只票的通知冷却时间（秒）
NOTIFY_COOLDOWN = 300  # 5 分钟

# macOS 系统提示音路径
_SOUND_DIR = Path("/System/Library/Sounds")
_DEFAULT_ALERT_SOUND = _SOUND_DIR / "Tink.aiff"
_URGENT_ALERT_SOUND = _SOUND_DIR / "Sosumi.aiff"


def send_desktop_notification(title: str, message: str, notify_type: str = "info") -> bool:
    """
    通过 catdesk notify 发送桌面通知。
    
    参数:
        title: 通知标题
        message: 通知正文
        notify_type: 通知类型 (info/warning/error)
    
    返回:
        是否发送成功
    """
    try:
        cmd = ["catdesk", "notify", "-t", title, "-m", message, "--type", notify_type]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            logger.debug(f"通知已发送: {title}")
            return True
        else:
            logger.warning(f"通知发送失败: {result.stderr}")
            return False
    except FileNotFoundError:
        logger.error("catdesk 命令不可用，无法发送通知")
        return False
    except subprocess.TimeoutExpired:
        logger.warning("通知发送超时")
        return False
    except Exception as e:
        logger.error(f"通知发送异常: {e}")
        return False


def play_alert_sound(urgent: bool = False):
    """
    播放系统提示音（macOS）。
    
    参数:
        urgent: 是否播放紧急提示音（用于止损/高分信号）
    """
    sound_file = _URGENT_ALERT_SOUND if urgent else _DEFAULT_ALERT_SOUND
    if not sound_file.exists():
        # 降级：尝试系统默认声音
        sound_file = _SOUND_DIR / "Glass.aiff"
        if not sound_file.exists():
            return
    
    try:
        subprocess.Popen(
            ["afplay", str(sound_file)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass  # 声音播放失败不影响主流程


def send_daxiang_notification(title: str, message: str, config: dict) -> bool:
    """
    通过大象消息推送通知。
    使用 catdesk CLI 的大象消息能力。
    
    参数:
        title: 消息标题
        message: 消息正文
        config: 大象消息配置（可包含 group_id 或 user_id）
    
    返回:
        是否发送成功
    """
    daxiang_config = config.get("notifications", {}).get("daxiang_config", {})
    target = daxiang_config.get("group_name") or daxiang_config.get("user_mis")
    
    if not target:
        logger.debug("大象推送未配置目标（group_name 或 user_mis），跳过")
        return False
    
    full_message = f"【PulseRadar】{title}\n{message}"
    
    try:
        cmd = ["catdesk", "daxiang", "send"]
        if daxiang_config.get("group_name"):
            cmd.extend(["--group", daxiang_config["group_name"]])
        elif daxiang_config.get("user_mis"):
            cmd.extend(["--user", daxiang_config["user_mis"]])
        cmd.extend(["--message", full_message])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.debug(f"大象消息已发送: {title}")
            return True
        else:
            logger.warning(f"大象消息发送失败: {result.stderr}")
            return False
    except FileNotFoundError:
        logger.debug("catdesk 命令不可用，无法发送大象消息")
        return False
    except Exception as e:
        logger.debug(f"大象消息发送异常: {e}")
        return False


def should_notify(stock_code: str) -> bool:
    """检查某只股票是否在冷却期内（去重）。"""
    now = time.time()
    last_time = _notify_cache.get(stock_code)
    if last_time and (now - last_time) < NOTIFY_COOLDOWN:
        return False
    return True


def mark_notified(stock_code: str):
    """标记某只股票已发送通知。"""
    _notify_cache[stock_code] = time.time()


def _describe_volume(volume_ratio: float | None) -> str:
    """把量比数值翻译成大白话。"""
    if volume_ratio is None or volume_ratio <= 0:
        return ""
    if volume_ratio >= 8:
        return f"交易量是平时的 {volume_ratio:.0f} 倍（极度活跃）"
    if volume_ratio >= 5:
        return f"交易量是平时的 {volume_ratio:.0f} 倍（非常活跃）"
    if volume_ratio >= 3:
        return f"交易量是平时的 {volume_ratio:.1f} 倍"
    if volume_ratio >= 1.5:
        return f"交易量放大到平时的 {volume_ratio:.1f} 倍"
    return ""


def _describe_score(score: float) -> str:
    """把异动评分翻译成可感知的强度描述。"""
    if score >= 85:
        return "强烈异动 ⚡"
    if score >= 70:
        return "明显异动"
    if score >= 60:
        return "值得关注"
    return "轻微异动"


def format_signal_notification(signal: dict) -> tuple[str, str]:
    """
    将异动信号格式化为通知的标题和正文。
    用大白话描述，避免专业术语。
    
    参数:
        signal: 异动信号字典，包含 stock_code, stock_name, signal_type,
                change_pct, volume_ratio, score 等字段
    
    返回:
        (title, message) 元组
    """
    signal_type = signal.get("signal_type", "异动")
    stock_name = signal.get("stock_name", "未知")
    stock_code = signal.get("stock_code", "000000")
    score = signal.get("score", 0)
    change_pct = signal.get("change_pct")
    volume_ratio = signal.get("volume_ratio")
    
    # 自选股标记
    is_watchlist = signal.get("is_watchlist", False)
    star = "⭐ " if is_watchlist else ""
    
    # 标题：简洁直白，说明发生了什么
    type_titles = {
        "涨速异动": "🔴 正在快速拉升",
        "量比突变": "🟡 突然放量",
        "涨停封板": "🟣 已涨停封板",
        "涨停炸板": "⚠️ 涨停打开了",
        "VWAP突破": "📈 放量突破均价线",
        "板块共振": "🔗 板块联动拉升",
        "封单强度": "🔒 涨停封单分析",
        "目标价到达": "🎯 到达目标价",
        "止损预警": "🚨 止损预警",
    }
    action = type_titles.get(signal_type, "📊 出现异动")
    title = f"{star}{action} · {stock_name}"
    
    # 正文：用自然语言描述
    lines = []
    
    # 第一行：涨跌幅 + 代码
    if change_pct is not None:
        sign = "+" if change_pct > 0 else ""
        direction = "涨" if change_pct > 0 else "跌"
        lines.append(f"当前{direction}幅 {sign}{change_pct:.1f}% ({stock_code})")
    else:
        lines.append(f"({stock_code})")
    
    # 第二行：交易量描述
    vol_desc = _describe_volume(volume_ratio)
    if vol_desc:
        lines.append(vol_desc)
    
    # 第三行：信号原因（如果有）
    reasons = signal.get("reasons", [])
    if reasons and signal_type in ("VWAP突破", "板块共振", "封单强度", "目标价到达", "止损预警"):
        lines.append(reasons[0])
    
    # 最后一行：异动强度
    score_desc = _describe_score(score)
    lines.append(f"{score_desc} ({score:.0f}分)")
    
    message = "\n".join(lines)
    
    return title, message


def notify_signal(signal: dict, config: dict) -> bool:
    """
    处理一个异动信号的通知推送。含去重检查。
    支持多渠道：桌面通知 + 大象消息 + 声音。
    
    参数:
        signal: 异动信号字典
        config: 通知配置
    
    返回:
        是否实际发送了通知
    """
    stock_code = signal.get("stock_code", "")
    
    # 去重检查
    if not should_notify(stock_code):
        logger.debug(f"通知冷却中，跳过: {stock_code}")
        return False
    
    notifications = config.get("notifications", {})
    notified = False
    title, message = format_signal_notification(signal)
    score = signal.get("score", 0)
    
    # 1. 桌面通知
    if notifications.get("desktop", True):
        notify_type = "warning" if score >= 80 else "info"
        if send_desktop_notification(title, message, notify_type):
            notified = True
    
    # 2. 大象消息推送
    if notifications.get("daxiang", False):
        send_daxiang_notification(title, message, config)
    
    # 3. 通知声音
    if notifications.get("sound", False) and notified:
        is_urgent = score >= 90 or signal.get("signal_type") in ("止损预警", "目标价到达")
        play_alert_sound(urgent=is_urgent)
    
    if notified:
        mark_notified(stock_code)
    
    return notified
