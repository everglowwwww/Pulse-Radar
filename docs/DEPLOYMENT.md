# PulseRadar 跨平台部署指南

本文档详细说明如何将 PulseRadar 部署到 CatDesk 以外的环境运行，包括脱离 Agent 直接运行、在 Cursor / Windsurf / Codex 等 AI Agent 平台上部署，以及在无 GUI 的服务器 / VPS 上部署。

---

## 1. 项目概述

PulseRadar 是一个 AI 盘中异动雷达，实时扫描自选股行情数据，检测涨速异动、量比突变、涨停 / 炸板、VWAP 突破等信号，并通过桌面通知、消息推送等方式提醒用户关注。

核心能力包括：

- 自选股实时行情监控（腾讯财经 API，无需认证）
- 多维度信号检测：涨速异动、量比突变、涨停 / 炸板、VWAP 突破、板块共振
- 综合评分系统（0-100 分），支持低 / 中 / 高三档灵敏度
- 自选股盯梢：低阈值推送、目标价提醒、止损预警
- 通知去重机制（同一只票 5 分钟冷却期）
- JSON 日志记录与今日异动汇总
- 交易时间自动判断（内置 A 股节假日日历），非交易时间自动暂停

技术栈：

- Python 3.12+
- uv（Astral 出品的 Python 包管理器，替代 pip + venv）
- akshare（A 股数据接口库，P1 板块共振信号依赖）
- requests（HTTP 请求，腾讯财经 API 数据拉取）
- pandas（数据处理）

项目结构：

```
Pulse-Radar/
├── pyproject.toml          # 项目配置与依赖声明
├── config.json             # 运行配置（轮询间隔、阈值、自选股、通知开关等）
├── SKILL.md                # CatPaw Skill 注册文件（仅 CatDesk 使用）
├── uv.lock                 # uv 依赖锁文件
├── docs/
│   └── DEPLOYMENT.md       # 本文档
├── output/                 # 运行时输出（日志、PID、状态文件）
└── src/
    ├── __init__.py
    ├── main.py             # CLI 入口（start/stop/status/today/watch/unwatch/watchlist）
    ├── scanner.py          # 扫描主循环（数据拉取 → 信号检测 → 通知推送）
    ├── signals.py          # P0 核心信号检测（涨速异动、量比突变、涨停/炸板）
    ├── signals_p1.py       # P1 增强信号检测（板块共振、封单强度、VWAP 突破）
    ├── scoring.py          # 综合评分系统
    ├── filters.py          # 基础过滤器（排除 ST、小市值、低成交等）
    ├── watchlist.py        # 自选股管理 + 盯梢逻辑
    ├── watchlist_report.py # 自选股行情播报 + 买点分析
    ├── notifier.py         # 通知推送模块（★ 与 CatDesk 耦合）
    ├── logger.py           # JSON 信号日志系统
    ├── holidays.py         # A 股交易日历（2025-2026 节假日）
    └── config_validator.py # 配置校验与默认值补全
```

---

## 2. 架构分析：与 CatDesk 的耦合点

PulseRadar 的核心业务逻辑完全独立，不依赖任何 Agent 平台。与 CatDesk 的耦合仅存在于通知推送层和 Skill 注册文件中。

### 2.1 耦合点清单

**耦合点 1：`notifier.py` — `send_desktop_notification()` 函数**

```python
# notifier.py 第 38 行
cmd = ["catdesk", "notify", "-t", title, "-m", message, "--type", notify_type]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
```

该函数通过调用 `catdesk notify` CLI 命令发送 macOS 桌面通知。被以下位置调用：

- `scanner.py` 第 416 行 — 启动时发送"PulseRadar 已启动"通知
- `scanner.py` 第 428 行 — 收盘自动停止时发送通知
- `watchlist_report.py` 第 273 行 — 自选股行情播报通知
- `watchlist_report.py` 第 287 行 — 自选股汇总通知
- `notifier.py` 第 261 行 — 异动信号通知（通过 `notify_signal()` 间接调用）

**耦合点 2：`notifier.py` — `send_daxiang_notification()` 函数**

```python
# notifier.py 第 104 行
cmd = ["catdesk", "daxiang", "send"]
```

该函数通过 `catdesk daxiang send` 命令向大象 IM 发送消息。仅在 `config.json` 中 `notifications.daxiang` 设为 `true` 时才会调用，默认关闭。

**耦合点 3：`notifier.py` — `play_alert_sound()` 函数**

```python
# notifier.py 第 72 行
subprocess.Popen(["afplay", str(sound_file)], ...)
```

该函数使用 macOS 原生的 `afplay` 命令播放提示音。这不是 CatDesk 依赖，但属于 macOS 专属依赖，在 Linux / Windows 上不可用。

**耦合点 4：`SKILL.md` — CatPaw Skill 注册**

`SKILL.md` 文件是 CatPaw / CatDesk 的 Skill 描述文件，定义了触发词和命令映射。这个文件仅用于 CatDesk 识别和调度 PulseRadar，项目代码本身不会加载它。在其他平台上部署时直接忽略即可。

### 2.2 独立模块（无任何平台依赖）

以下模块完全独立，可以在任何 Python 环境中运行：

| 模块 | 功能 | 外部依赖 |
|------|------|----------|
| `scanner.py` | 扫描主循环、数据拉取 | requests, pandas（腾讯 API） |
| `signals.py` | P0 信号检测 | pandas |
| `signals_p1.py` | P1 增强信号 | akshare, pandas |
| `scoring.py` | 综合评分 | 无 |
| `filters.py` | 股票过滤 | pandas |
| `watchlist.py` | 自选股管理 | 无 |
| `watchlist_report.py` | 行情播报生成 | pandas |
| `logger.py` | JSON 日志 | 无 |
| `holidays.py` | 交易日历 | 无 |
| `config_validator.py` | 配置校验 | 无 |
| `main.py` | CLI 入口 | 无 |

结论：要将 PulseRadar 部署到其他平台，只需要替换 `notifier.py` 中的通知实现，其余代码无需改动。

---

## 3. 通用部署方案（脱离 Agent 直接运行）

适用于 macOS 本地开发机，不依赖任何 AI Agent 平台。

### 3.1 安装 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

安装完成后，确保 `uv` 在 PATH 中：

```bash
# 添加到 shell 配置（zsh）
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# 验证
uv --version
```

### 3.2 克隆项目并安装依赖

```bash
cd /path/to/your/workspace
git clone <your-repo-url> Pulse-Radar
cd Pulse-Radar
uv sync
```

`uv sync` 会自动创建 `.venv` 虚拟环境并安装 `pyproject.toml` 中声明的所有依赖。

### 3.3 修改通知实现

将 `notifier.py` 中的 `send_desktop_notification()` 函数替换为 macOS 原生 `osascript` 通知：

```python
def send_desktop_notification(title: str, message: str, notify_type: str = "info") -> bool:
    """
    通过 macOS 原生 osascript 发送桌面通知。
    替代原来的 catdesk notify 命令。
    """
    try:
        # 转义双引号
        safe_title = title.replace('"', '\\"')
        safe_message = message.replace('"', '\\"')
        script = (
            f'display notification "{safe_message}" '
            f'with title "{safe_title}"'
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            logger.debug(f"通知已发送: {title}")
            return True
        else:
            logger.warning(f"通知发送失败: {result.stderr}")
            return False
    except FileNotFoundError:
        logger.error("osascript 命令不可用（仅 macOS 支持）")
        return False
    except subprocess.TimeoutExpired:
        logger.warning("通知发送超时")
        return False
    except Exception as e:
        logger.error(f"通知发送异常: {e}")
        return False
```

如果安装了 [terminal-notifier](https://github.com/julienXX/terminal-notifier)，也可以使用它（支持更多自定义选项）：

```bash
# 安装
brew install terminal-notifier
```

```python
def send_desktop_notification(title: str, message: str, notify_type: str = "info") -> bool:
    """通过 terminal-notifier 发送桌面通知。"""
    try:
        cmd = [
            "terminal-notifier",
            "-title", title,
            "-message", message,
            "-sound", "Glass",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except FileNotFoundError:
        logger.error("terminal-notifier 未安装，请运行: brew install terminal-notifier")
        return False
    except Exception as e:
        logger.error(f"通知发送异常: {e}")
        return False
```

同时，`send_daxiang_notification()` 函数在不使用 CatDesk 时可以改为空实现（直接返回 `False`），或替换为其他消息推送方案（见第 5 节）。

### 3.4 配置自选股

编辑 `config.json`，在 `watchlist.stocks` 中添加你关注的股票：

```json
{
  "watchlist": {
    "enabled": true,
    "stocks": [
      {
        "code": "603986",
        "name": "兆易创新",
        "stop_loss": 85.0,
        "target_price": 120.0
      }
    ],
    "push_threshold": 30,
    "midday_summary": true
  }
}
```

### 3.5 启动运行

```bash
# 前台运行（调试用，可看到实时日志）
uv run python -m src.main start --foreground --verbose

# 后台运行
nohup uv run python -m src.main start --foreground > output/console.log 2>&1 &

# 查看状态
uv run python -m src.main status

# 停止
uv run python -m src.main stop

# 查看今日异动汇总
uv run python -m src.main today
```

---

## 4. 在 Cursor / Windsurf / Codex 上部署

Cursor、Windsurf、Codex 等 AI 编程工具本质上提供了一个终端环境，可以像在普通 terminal 中一样运行 PulseRadar。

### 4.1 项目准备

将项目文件夹拖入 Agent 的工作区，或通过 git clone：

```bash
git clone <your-repo-url> Pulse-Radar
```

在 Agent 的终端中执行：

```bash
cd Pulse-Radar

# 安装 uv（如果尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# 安装依赖
uv sync
```

### 4.2 通知方案

macOS 环境下，按第 3.3 节替换为 `osascript` 通知即可。

如果需要跨平台通知（Windows / Linux），推荐使用飞书 Webhook：

```python
import requests

def send_desktop_notification(title: str, message: str, notify_type: str = "info") -> bool:
    """通过飞书 Webhook 推送通知。"""
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL", "")
    if not webhook_url:
        logger.debug("未配置 FEISHU_WEBHOOK_URL，跳过通知")
        return False
    try:
        payload = {
            "msg_type": "text",
            "content": {
                "text": f"【PulseRadar】{title}\n{message}"
            }
        }
        resp = requests.post(webhook_url, json=payload, timeout=5)
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"飞书通知发送异常: {e}")
        return False
```

使用前设置环境变量：

```bash
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx"
```

### 4.3 配置为自动任务

部分 Agent 支持自定义 task / command，可以将启动命令配置为快捷任务：

Cursor（`.cursor/tasks.json` 示例）：

```json
{
  "tasks": [
    {
      "label": "PulseRadar Start",
      "command": "cd ${workspaceFolder} && uv run python -m src.main start --foreground --verbose",
      "type": "shell"
    },
    {
      "label": "PulseRadar Stop",
      "command": "cd ${workspaceFolder} && uv run python -m src.main stop",
      "type": "shell"
    },
    {
      "label": "PulseRadar Status",
      "command": "cd ${workspaceFolder} && uv run python -m src.main status",
      "type": "shell"
    }
  ]
}
```

也可以直接用自然语言指示 Agent 执行：在 Cursor / Windsurf 的对话中输入"启动 PulseRadar"，Agent 会在终端中执行相应命令。

---

## 5. 在服务器 / VPS 上部署（无 GUI 环境）

在无桌面环境的服务器上，`osascript`、`afplay` 等命令不可用，通知必须改为远程推送方案。

### 5.1 通知方案：远程推送

选择以下任一方案：

**方案 A：飞书 Webhook（推荐）**

创建飞书自定义机器人，获取 Webhook URL，然后在 `notifier.py` 中替换通知函数（见第 4.2 节代码）。

**方案 B：Server酱（微信推送）**

```python
def send_desktop_notification(title: str, message: str, notify_type: str = "info") -> bool:
    """通过 Server酱 推送到微信。"""
    sckey = os.environ.get("SERVERCHAN_SCKEY", "")
    if not sckey:
        return False
    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{sckey}.send",
            data={"title": title, "desp": message},
            timeout=5
        )
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"Server酱通知异常: {e}")
        return False
```

```bash
export SERVERCHAN_SCKEY="SCTxxxxxxxxxxx"
```

**方案 C：PushPlus（微信推送）**

```python
def send_desktop_notification(title: str, message: str, notify_type: str = "info") -> bool:
    """通过 PushPlus 推送到微信。"""
    token = os.environ.get("PUSHPLUS_TOKEN", "")
    if not token:
        return False
    try:
        resp = requests.post(
            "http://www.pushplus.plus/send",
            json={"token": token, "title": title, "content": message},
            timeout=5
        )
        return resp.json().get("code") == 200
    except Exception as e:
        logger.error(f"PushPlus通知异常: {e}")
        return False
```

```bash
export PUSHPLUS_TOKEN="your_token_here"
```

**禁用声音播放**：在 `config.json` 中将 `notifications.sound` 设为 `false`，或修改 `play_alert_sound()` 函数使其在非 macOS 环境下直接返回：

```python
def play_alert_sound(urgent: bool = False):
    """播放系统提示音（仅 macOS）。"""
    import platform
    if platform.system() != "Darwin":
        return  # 非 macOS 环境，跳过
    # ... 原有逻辑
```

### 5.2 使用 systemd 管理进程

创建 systemd service 文件：

```bash
sudo tee /etc/systemd/system/pulse-radar.service << 'EOF'
[Unit]
Description=PulseRadar — AI 盘中异动雷达
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/home/your_username/Pulse-Radar
Environment=PATH=/home/your_username/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx
ExecStart=/home/your_username/.local/bin/uv run python -m src.main start --foreground
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable pulse-radar
sudo systemctl start pulse-radar

# 查看状态
sudo systemctl status pulse-radar

# 查看日志
sudo journalctl -u pulse-radar -f

# 停止
sudo systemctl stop pulse-radar
```

PulseRadar 内置了交易时间判断（09:25-15:05，工作日），非交易时间会自动进入休眠等待状态，不会频繁请求 API。`auto_stop_after_close` 配置为 `true` 时会在收盘后自动退出主循环，systemd 的 `Restart=on-failure` 会在进程退出后自动重启，但因为是正常退出（returncode=0），不会触发重启。如果希望每个交易日都自动运行，使用下面的 crontab 方案。

### 5.3 使用 crontab 定时启停

```bash
# 编辑 crontab
crontab -e
```

添加以下条目（假设项目在 `/home/your_username/Pulse-Radar`）：

```crontab
# PulseRadar：每个交易日 09:25 启动
25 9 * * 1-5 cd /home/your_username/Pulse-Radar && /home/your_username/.local/bin/uv run python -m src.main start --foreground >> output/console.log 2>&1 &

# PulseRadar：每个交易日 15:10 停止（兜底，防止进程残留）
10 15 * * 1-5 cd /home/your_username/Pulse-Radar && /home/your_username/.local/bin/uv run python -m src.main stop
```

注意：crontab 不会自动跳过节假日。PulseRadar 内置了交易日历判断（`holidays.py`），非交易日启动后会自动进入休眠等待状态，不会产生无效请求。但为节省资源，可以在节假日前后手动停止。

如果希望更精确地控制启停，可以编写一个包装脚本：

```bash
#!/bin/bash
# /home/your_username/Pulse-Radar/scripts/start_if_trading_day.sh

cd /home/your_username/Pulse-Radar
export PATH="$HOME/.local/bin:$PATH"

# 检查是否为交易日（简单判断：周末不启动）
DAY_OF_WEEK=$(date +%u)
if [ "$DAY_OF_WEEK" -gt 5 ]; then
    echo "周末，跳过"
    exit 0
fi

# 启动 PulseRadar
uv run python -m src.main start --foreground >> output/console.log 2>&1 &
```

然后在 crontab 中调用：

```crontab
25 9 * * 1-5 /home/your_username/Pulse-Radar/scripts/start_if_trading_day.sh
```

---

## 6. 通知适配层设计

为了在不同环境间无缝切换，建议将 `notifier.py` 重构为插件式设计，通过 `config.json` 选择通知后端，避免修改代码。

### 6.1 抽象接口

```python
# src/notification_backend.py
from abc import ABC, abstractmethod


class NotificationBackend(ABC):
    """通知后端抽象接口。"""

    @abstractmethod
    def send(self, title: str, message: str, notify_type: str = "info") -> bool:
        """发送通知。返回是否成功。"""
        ...
```

### 6.2 实现多个 Backend

```python
# src/notification_backends.py
import os
import subprocess
import logging
import requests

from .notification_backend import NotificationBackend

logger = logging.getLogger(__name__)


class CatDeskBackend(NotificationBackend):
    """CatDesk 桌面通知（原方案）。"""

    def send(self, title: str, message: str, notify_type: str = "info") -> bool:
        try:
            cmd = ["catdesk", "notify", "-t", title, "-m", message, "--type", notify_type]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"CatDesk通知异常: {e}")
            return False


class OSAScriptBackend(NotificationBackend):
    """macOS 原生 osascript 通知。"""

    def send(self, title: str, message: str, notify_type: str = "info") -> bool:
        try:
            safe_title = title.replace('"', '\\"')
            safe_message = message.replace('"', '\\"')
            script = f'display notification "{safe_message}" with title "{safe_title}"'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"osascript通知异常: {e}")
            return False


class FeishuWebhookBackend(NotificationBackend):
    """飞书 Webhook 推送。"""

    def __init__(self, webhook_url: str = ""):
        self.webhook_url = webhook_url or os.environ.get("FEISHU_WEBHOOK_URL", "")

    def send(self, title: str, message: str, notify_type: str = "info") -> bool:
        if not self.webhook_url:
            logger.debug("飞书 Webhook 未配置，跳过")
            return False
        try:
            payload = {
                "msg_type": "text",
                "content": {"text": f"【PulseRadar】{title}\n{message}"}
            }
            resp = requests.post(self.webhook_url, json=payload, timeout=5)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"飞书通知异常: {e}")
            return False


class ServerChanBackend(NotificationBackend):
    """Server酱（微信推送）。"""

    def __init__(self, sckey: str = ""):
        self.sckey = sckey or os.environ.get("SERVERCHAN_SCKEY", "")

    def send(self, title: str, message: str, notify_type: str = "info") -> bool:
        if not self.sckey:
            return False
        try:
            resp = requests.post(
                f"https://sctapi.ftqq.com/{self.sckey}.send",
                data={"title": title, "desp": message},
                timeout=5
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Server酱通知异常: {e}")
            return False
```

### 6.3 Backend 工厂与配置

在 `config.json` 中新增 `notification_backend` 字段：

```json
{
  "notifications": {
    "desktop": true,
    "sound": true,
    "backend": "osascript",
    "backend_config": {
      "feishu_webhook_url": "",
      "serverchan_sckey": ""
    }
  }
}
```

`backend` 字段可选值：`catdesk`、`osascript`、`feishu`、`serverchan`。

在 `notifier.py` 中添加工厂函数：

```python
from .notification_backends import (
    CatDeskBackend,
    OSAScriptBackend,
    FeishuWebhookBackend,
    ServerChanBackend,
)

_BACKENDS = {
    "catdesk": CatDeskBackend,
    "osascript": OSAScriptBackend,
    "feishu": FeishuWebhookBackend,
    "serverchan": ServerChanBackend,
}

_backend_instance: NotificationBackend | None = None


def get_backend(config: dict) -> NotificationBackend:
    """根据配置获取通知后端实例（单例）。"""
    global _backend_instance
    if _backend_instance is not None:
        return _backend_instance

    notifications = config.get("notifications", {})
    backend_name = notifications.get("backend", "catdesk")
    backend_cls = _BACKENDS.get(backend_name, CatDeskBackend)

    backend_config = notifications.get("backend_config", {})
    if backend_name == "feishu":
        _backend_instance = FeishuWebhookBackend(
            webhook_url=backend_config.get("feishu_webhook_url", "")
        )
    elif backend_name == "serverchan":
        _backend_instance = ServerChanBackend(
            sckey=backend_config.get("serverchan_sckey", "")
        )
    else:
        _backend_instance = backend_cls()

    return _backend_instance


def send_desktop_notification(title: str, message: str, notify_type: str = "info",
                               config: dict | None = None) -> bool:
    """发送桌面通知（通过配置的后端）。"""
    if config is None:
        # 兜底：使用 CatDesk
        backend = CatDeskBackend()
    else:
        backend = get_backend(config)
    return backend.send(title, message, notify_type)
```

注意：现有代码中 `send_desktop_notification` 的调用点（`scanner.py`、`watchlist_report.py`）需要传入 `config` 参数。如果不想修改所有调用点，可以在模块初始化时设置全局 config，或使用环境变量传递 backend 选择。

这样切换部署环境时，只需修改 `config.json` 中的 `backend` 字段，无需改动任何代码。

---

## 7. 注意事项

**腾讯财经 API 无需认证**：PulseRadar 的核心数据源是腾讯财经实时行情接口（`https://qt.gtimg.cn/q=...`），不需要任何 API Key 或认证，任何能访问互联网的环境都能调用。P1 板块共振信号依赖的 AKShare 库同样使用公开接口。

**海外服务器地域限制**：腾讯财经 API 和 AKShare 底层调用的东方财富接口主要面向中国大陆用户。如果部署在海外服务器，可能会遇到以下情况：响应延迟较高（建议将轮询间隔适当加大）、部分接口可能返回空数据或超时（建议增加重试和超时容忍）、极端情况下 IP 可能被限制访问（建议使用大陆节点或配置代理）。如果只需要自选股监控（不使用 P1 板块共振），可以注释掉 `signals_p1.py` 中对 akshare 的调用，仅保留腾讯 API 数据源。

**output 目录写权限**：PulseRadar 运行时需要在 `output_dir`（默认 `./output`）中写入日志文件（`pulse-radar.log`）、PID 文件（`pulse-radar.pid`）、状态文件（`status.json`）和每日信号记录（`pulse-radar-YYYY-MM-DD.json`）。确保运行用户对该目录有写权限：

```bash
mkdir -p output
chmod 755 output
```

如果使用 systemd，确保 `WorkingDirectory` 指向项目根目录，且 `User` 指定的用户对项目目录有读写权限。

**Python 3.12+ 和 uv 是唯一依赖**：PulseRadar 不依赖任何系统级库或 C 扩展（akshare、requests、pandas 都是纯 Python 或有预编译 wheel）。只要安装了 Python 3.12+ 和 uv，执行 `uv sync` 即可完成全部依赖安装，不需要系统包管理器额外安装任何东西。

**macOS 提示音依赖**：`play_alert_sound()` 函数使用 macOS 原生的 `afplay` 命令和 `/System/Library/Sounds/` 下的音频文件。在 Linux / Windows 上该功能不可用，但不影响主流程。建议在非 macOS 环境下将 `config.json` 中 `notifications.sound` 设为 `false`，或修改该函数在非 macOS 环境下直接返回。

**交易日历维护**：`holidays.py` 中硬编码了 2025-2026 年的 A 股休市安排。2026 年的日期为预估，每年年底国务院发布正式公告后需要核实更新。如果部署为长期运行的服务，注意在新年份到来前更新节假日数据。

**并发运行防护**：PulseRadar 通过 PID 文件（`output/pulse-radar.pid`）防止重复启动。如果进程异常退出未清理 PID 文件，下次启动时会检测到 PID 对应的进程已不存在，自动清理并正常启动。无需手动干预。

**反爬退避机制**：当 API 连续请求失败时（可能是触发了反爬限制），PulseRadar 会自动启用指数退避策略，从 30 秒开始翻倍，最长 300 秒（5 分钟）。正常情况下自选股数量少（通常 < 20 只），单次请求即可完成，对 API 压力极小，不易触发反爬。
