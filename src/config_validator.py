"""
config_validator.py – PulseRadar 配置校验与填充模块
=====================================================
提供 validate_config / sanitize_config 两个核心函数。

设计原则：**宽容优先**
  - 缺失字段不视为错误，由 sanitize_config 用默认值补齐。
  - 仅当字段存在但值明显非法时才报错。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple

# ────────────────────────────────────────────────────────────
# 默认配置（缺省值参考）
# ────────────────────────────────────────────────────────────
DEFAULTS: Dict[str, Any] = {
    "poll_interval": 5,            # 轮询间隔（秒），>= 3
    "push_threshold": 60,          # 推送阈值，0-100
    "sensitivity": "medium",       # 灵敏度：low / medium / high
    "filters": {},                 # 过滤参数，值应为数值
    "watchlist": {
        "stocks": [],              # [{"code": "...", "name": "..."}]
        "push_threshold": 60,      # 自选股推送阈值，0-100
    },
    "notifications": {
        "desktop": True,
        "sound": False,
    },
    "output_dir": "./output",      # 输出目录
}

_VALID_SENSITIVITIES = {"low", "medium", "high"}


def validate_config(config: dict) -> Tuple[bool, List[str]]:
    """
    校验配置字典，返回 (is_valid, errors)。

    校验策略：只有字段**存在且值非法**才记为错误；字段缺失不报错
    （由 sanitize_config 补默认值）。

    Parameters
    ----------
    config : dict
        用户提供的配置字典。

    Returns
    -------
    tuple[bool, list[str]]
        (True, []) 表示配置合法；(False, [...]) 附带所有错误描述。
    """
    errors: List[str] = []

    # ── poll_interval ──
    if "poll_interval" in config:
        val = config["poll_interval"]
        if not isinstance(val, int):
            errors.append(f"poll_interval 必须为整数，当前类型为 {type(val).__name__}")
        elif val < 3:
            errors.append(f"poll_interval 不得小于 3，当前值为 {val}")

    # ── push_threshold（顶层） ──
    if "push_threshold" in config:
        val = config["push_threshold"]
        if not isinstance(val, int):
            errors.append(f"push_threshold 必须为整数，当前类型为 {type(val).__name__}")
        elif not (0 <= val <= 100):
            errors.append(f"push_threshold 必须在 0-100 之间，当前值为 {val}")

    # ── sensitivity ──
    if "sensitivity" in config:
        val = config["sensitivity"]
        if val not in _VALID_SENSITIVITIES:
            errors.append(
                f"sensitivity 必须为 {'/'.join(sorted(_VALID_SENSITIVITIES))} 之一，"
                f"当前值为 {val!r}"
            )

    # ── filters ──
    if "filters" in config:
        val = config["filters"]
        if not isinstance(val, dict):
            errors.append(f"filters 必须为字典，当前类型为 {type(val).__name__}")
        else:
            for k, v in val.items():
                if not isinstance(v, (int, float)):
                    errors.append(
                        f"filters[{k!r}] 的值必须为数值，"
                        f"当前类型为 {type(v).__name__}"
                    )

    # ── watchlist ──
    if "watchlist" in config:
        wl = config["watchlist"]
        if not isinstance(wl, dict):
            errors.append(f"watchlist 必须为字典，当前类型为 {type(wl).__name__}")
        else:
            # watchlist.stocks
            if "stocks" in wl:
                stocks = wl["stocks"]
                if not isinstance(stocks, list):
                    errors.append(
                        f"watchlist.stocks 必须为列表，"
                        f"当前类型为 {type(stocks).__name__}"
                    )
                else:
                    for i, item in enumerate(stocks):
                        if not isinstance(item, dict):
                            errors.append(
                                f"watchlist.stocks[{i}] 必须为字典，"
                                f"当前类型为 {type(item).__name__}"
                            )
                            continue
                        if "code" not in item or not isinstance(item.get("code"), str):
                            errors.append(
                                f"watchlist.stocks[{i}] 缺少合法的 code（字符串）"
                            )
                        if "name" not in item or not isinstance(item.get("name"), str):
                            errors.append(
                                f"watchlist.stocks[{i}] 缺少合法的 name（字符串）"
                            )

            # watchlist.push_threshold
            if "push_threshold" in wl:
                val = wl["push_threshold"]
                if not isinstance(val, int):
                    errors.append(
                        f"watchlist.push_threshold 必须为整数，"
                        f"当前类型为 {type(val).__name__}"
                    )
                elif not (0 <= val <= 100):
                    errors.append(
                        f"watchlist.push_threshold 必须在 0-100 之间，当前值为 {val}"
                    )

    # ── notifications ──
    if "notifications" in config:
        val = config["notifications"]
        if not isinstance(val, dict):
            errors.append(
                f"notifications 必须为字典，当前类型为 {type(val).__name__}"
            )
        else:
            for k, v in val.items():
                if not isinstance(v, bool):
                    errors.append(
                        f"notifications[{k!r}] 的值必须为布尔值，"
                        f"当前类型为 {type(v).__name__}"
                    )

    # ── output_dir ──
    if "output_dir" in config:
        val = config["output_dir"]
        if not isinstance(val, str) or not val.strip():
            errors.append("output_dir 必须为非空字符串")

    is_valid = len(errors) == 0
    return is_valid, errors


def sanitize_config(config: dict) -> dict:
    """
    对配置字典进行清洗与补全，缺失字段用默认值填充。

    不会修改原始字典，返回一份深拷贝。

    Parameters
    ----------
    config : dict
        用户提供的（可能不完整的）配置字典。

    Returns
    -------
    dict
        补全后的配置字典。
    """
    result = deepcopy(DEFAULTS)

    # 顶层简单字段
    for key in ("poll_interval", "push_threshold", "sensitivity", "output_dir"):
        if key in config:
            result[key] = config[key]

    # filters：合并用户提供的键值
    if "filters" in config and isinstance(config["filters"], dict):
        result["filters"] = deepcopy(config["filters"])

    # watchlist：逐字段合并
    if "watchlist" in config and isinstance(config["watchlist"], dict):
        user_wl = config["watchlist"]
        if "stocks" in user_wl and isinstance(user_wl["stocks"], list):
            result["watchlist"]["stocks"] = deepcopy(user_wl["stocks"])
        if "push_threshold" in user_wl:
            result["watchlist"]["push_threshold"] = user_wl["push_threshold"]

    # notifications：合并用户提供的键值
    if "notifications" in config and isinstance(config["notifications"], dict):
        result["notifications"].update(deepcopy(config["notifications"]))

    return result
