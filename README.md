# PulseRadar — A 股盘中异动雷达 📡

> 像一个经验丰富的操盘手坐在你旁边，平时安静不打扰，一有异动立刻拍你肩膀：「这个值得看一眼」。

PulseRadar 是一个**自选股实时行情监控工具**，通过腾讯财经 API 拉取自选股实时数据，进行多维度异动信号检测和买点分析，并通过桌面通知推送行情播报。交易时间内每 5 分钟自动扫描一次，收盘后自动停止。

## 核心能力

**实时行情拉取** — 通过腾讯财经 API（`qt.gtimg.cn`）获取自选股实时行情，包括价格、涨跌幅、成交量、成交额、量比、换手率、市盈率、市净率等完整字段。5 只自选股仅需 1 次 HTTP 请求，耗时 < 1 秒。

**多维度异动信号检测** — 不是简单看涨幅，而是综合多个维度的信号融合：

- 涨速异动：涨速 > 2%/min 且量比 > 1.5（排除缩量假突破）
- 量比突变：突然放量（量比 > 3），捕捉资金异动的早期信号
- 目标价到达：价格触及预设目标价时推送 🎯 提醒
- 止损预警：跌破预设止损线时推送 🚨 预警
- VWAP 突破：放量上穿成交量加权均价线

**7 维买点分析** — 每轮播报对每只自选股进行多维度买点评估（涨跌幅位置、量比资金参与度、换手率流动性、分时强度、涨速动能、5 分钟趋势、资金流向），给出 🟢🟡⚪🔴 四档综合建议。

**智能运行管理** — 仅交易日 09:25-15:05 运行，非交易时间自动暂停，15:05 收盘后自动停止并推送收盘汇总。内置节假日判断，无需手动管理。

## 通知效果

每 5 分钟推送一轮自选股行情，每只股票一条独立通知：

```
⭐ 中矿资源 +9.99% · 58.99
成交 34.8万手 · 20.5亿 | 量比 2.2 | 换手 5.1%
—— 🟢 多维共振，可考虑介入
✅ 量比 2.2 放量配合
```

```
⭐ 🎯 到达目标价 · 兆易创新
当前涨幅 +5.2% (603986)
交易量是平时的 4.3 倍
明显异动 (78分)
```

## 快速开始

### 环境要求

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)（Python 包管理器）
- macOS（桌面通知依赖 `catdesk notify` 或 `osascript`）

### 安装

```bash
# 安装 uv（如果还没有）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 克隆项目
git clone https://github.com/everglowwwww/Pulse-Radar.git
cd Pulse-Radar

# 安装依赖
uv sync
```

### 配置自选股

编辑 `config.json`，在 `watchlist.stocks` 中添加你要监控的股票：

```json
{
  "watchlist": {
    "stocks": [
      {
        "code": "603986",
        "name": "兆易创新",
        "stop_loss": 85.0,
        "target_price": 120.0
      },
      {
        "code": "002240",
        "name": "盛新锂能",
        "stop_loss": null,
        "target_price": null
      }
    ]
  }
}
```

每只股票可选设 `target_price`（目标价，到达时推送提醒）和 `stop_loss`（止损价，跌破时推送预警）。

### 启动

```bash
# 前台启动（推荐调试时使用，Ctrl+C 停止）
uv run python -m src.main start --foreground --verbose

# 后台启动
uv run python -m src.main start

# 查看运行状态
uv run python -m src.main status

# 停止
uv run python -m src.main stop

# 查看今日异动汇总
uv run python -m src.main today
```

### 自选股管理

```bash
# 添加自选股
uv run python -m src.main watch 603986 --name 兆易创新 --target-price 120.0 --stop-loss 85.0

# 移除自选股
uv run python -m src.main unwatch 603986

# 查看自选股列表
uv run python -m src.main watchlist
```

## 配置说明

`config.json` 完整配置项：

| 配置项 | 默认值 | 说明 |
|-------|--------|------|
| `poll_interval` | 300 | 轮询间隔（秒），即两次拉取之间的最小间隔 |
| `push_threshold` | 60 | 异动信号推送阈值（0-100），越高越严格 |
| `sensitivity` | medium | 灵敏度预设（low / medium / high） |
| `auto_stop_after_close` | true | 15:05 收盘后是否自动停止 |
| `watchlist_report_interval` | 300 | 行情播报间隔（秒） |
| `output_dir` | ./output | 运行时输出目录（日志、PID、状态文件） |

灵敏度说明：
- **high** — 更多推送，涨速阈值 1.5%/min，适合积极交易者
- **medium** — 平衡模式，涨速阈值 2%/min（默认）
- **low** — 只推送最强信号，涨速阈值 3%/min，适合低频关注

## 项目结构

```
Pulse-Radar/
├── config.json              # 运行配置（自选股、轮询间隔、通知设置）
├── pyproject.toml            # Python 项目配置
├── src/
│   ├── main.py               # CLI 入口（start/stop/status/today/watch）
│   ├── scanner.py             # 核心引擎（数据拉取、扫描循环、自动停止）
│   ├── signals.py             # P0 信号检测（涨速异动、量比突变）
│   ├── signals_p1.py          # P1 信号检测（VWAP 突破、板块共振、封单强度）
│   ├── scoring.py             # 综合评分系统（信号融合、置信度调整）
│   ├── filters.py             # 股票过滤器（排除 ST、低市值、低流动性）
│   ├── watchlist.py           # 自选股管理（WatchlistManager + WatchlistGuard）
│   ├── watchlist_report.py    # 行情播报 + 7维买点分析
│   ├── notifier.py            # 通知推送（桌面通知、大象消息、声音提醒）
│   ├── logger.py              # 异动日志记录
│   ├── holidays.py            # A 股交易日历（节假日判断）
│   └── config_validator.py    # 配置文件校验
├── tests/                     # 单元测试
├── docs/
│   ├── DEPLOYMENT.md          # 跨平台部署方案（Cursor/Codex/服务器）
│   └── FEISHU_PLAN.md         # 飞书通知开发方案
└── output/                    # 运行时输出（日志、PID、状态，已 gitignore）
```

## 数据来源

使用腾讯财经 API（`qt.gtimg.cn`），无需 API Key，无需注册，公开免费。每次请求返回 88 个字段，覆盖价格、成交量、量比、换手率、市盈率、市净率、流通市值等完整行情数据。

当前配置下（5 只自选股，5 分钟轮询），每天仅约 48 次 HTTP 请求，远低于任何反爬阈值。

## 跨平台部署

PulseRadar 的核心逻辑（数据拉取、信号检测、行情分析）完全独立，不依赖任何 AI Agent 平台。与 CatDesk 的耦合仅限于 `notifier.py` 中的桌面通知调用，替换为 `osascript`（macOS 原生）或飞书 Webhook 即可在任何环境运行。

详见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — 覆盖独立运行、Cursor/Windsurf/Codex 部署、服务器 systemd 部署等方案。

详见 [docs/FEISHU_PLAN.md](docs/FEISHU_PLAN.md) — 飞书群机器人通知的完整开发方案（含代码）。

## 免责声明

本工具仅供个人学习和研究使用。所有推送信号均为 AI 分析结果，**不构成任何投资建议**。股市有风险，投资需谨慎。数据来源为公开免费接口，请遵守相关服务条款，控制请求频率。

## License

MIT
