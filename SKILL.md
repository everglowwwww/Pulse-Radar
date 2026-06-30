---
name: pulse-radar
description: >-
  AI 盘中异动雷达。实时扫描全市场 A 股，检测涨速异动、量比突变、涨停/炸板等信号，
  通过桌面通知推送值得关注的异动。
  当用户提到"开始盯盘""启动雷达""PulseRadar""停止盯盘""关闭雷达"
  "雷达状态""盯盘状态""今日异动""异动汇总""调整灵敏度"
  "盯住 XXX""关注 XXX""取消盯住""我的自选""盯梢列表"时使用。
  不用于盘前分析（用 market-radar）、个股交易建议、量化策略回测。
metadata:
  skillhub:
    creator: lipeilin06
---

# PulseRadar — AI 盘中异动雷达

## 项目路径

- 项目目录：`/Users/peilinli/Desktop/Vibecoding/Pulse-Radar`
- Python 入口：`src/main.py`
- 配置文件：`config.json`
- 输出目录：`~/Desktop/PulseRadar`（PID 文件、状态文件、日志在此）
- 虚拟环境：`.venv`（由 uv 管理）

## 运行方式

所有命令通过 `uv run` 在项目虚拟环境中执行：

```bash
cd /Users/peilinli/Desktop/Vibecoding/Pulse-Radar
export PATH="$HOME/.local/bin:$PATH"

# 启动盯盘（前台，调试用）
uv run python -m src.main start --foreground --verbose

# 停止盯盘
uv run python -m src.main stop

# 查看运行状态
uv run python -m src.main status

# 查看今日异动汇总
uv run python -m src.main today
```

## 用户指令映射

根据用户的自然语言指令，执行对应的命令：

### 启动类

触发词：「开始盯盘」「启动雷达」「PulseRadar 启动」「start」

操作：
1. 先执行 `uv run python -m src.main status` 检查是否已在运行
2. 如果未运行，执行以下命令在后台启动（**必须用后台模式**）：
   ```bash
   cd /Users/peilinli/Desktop/Vibecoding/Pulse-Radar && export PATH="$HOME/.local/bin:$PATH" && nohup uv run python -m src.main start --foreground > ~/Desktop/PulseRadar/console.log 2>&1 &
   ```
3. 等待 2 秒后检查状态确认启动成功
4. 回复用户启动结果

### 停止类

触发词：「停止盯盘」「关闭雷达」「PulseRadar 停止」「stop」

操作：
1. 执行 `cd /Users/peilinli/Desktop/Vibecoding/Pulse-Radar && export PATH="$HOME/.local/bin:$PATH" && uv run python -m src.main stop`
2. 回复用户已停止

### 状态查询类

触发词：「雷达状态」「盯盘状态」「PulseRadar 状态」「status」

操作：
1. 执行 `cd /Users/peilinli/Desktop/Vibecoding/Pulse-Radar && export PATH="$HOME/.local/bin:$PATH" && uv run python -m src.main status`
2. 读取 `~/Desktop/PulseRadar/status.json` 获取详细信息
3. 以友好格式回复用户

### 今日异动汇总

触发词：「今日异动」「异动汇总」「today」

操作：
1. 执行 `cd /Users/peilinli/Desktop/Vibecoding/Pulse-Radar && export PATH="$HOME/.local/bin:$PATH" && uv run python -m src.main today`
2. 将结果以表格/列表形式回复用户

### 灵敏度调整

触发词：「调整灵敏度」「更敏感」「更迟钝」

操作：
1. 读取 `config.json`
2. 修改 `sensitivity` 字段（low / medium / high）
3. 告知用户需要重启雷达才能生效
4. 解释三个级别的差异：
   - high：更多推送，可能有更多噪音（涨速阈值 1.5%/min）
   - medium（默认）：平衡模式（涨速阈值 2%/min）
   - low：更少推送，只推送最强信号（涨速阈值 3%/min）

### 自选股管理

触发词：「盯住 XXX」「关注 XXX」→ 添加自选股
触发词：「取消盯住 XXX」「不再关注 XXX」→ 移除自选股
触发词：「我的自选」「盯梢列表」「自选股」→ 查看列表

操作：
```bash
cd /Users/peilinli/Desktop/Vibecoding/Pulse-Radar && export PATH="$HOME/.local/bin:$PATH"

# 添加自选股（需先查询股票代码和名称）
uv run python -m src.main watch <代码> --name <名称> [--target-price <目标价>] [--stop-loss <止损价>]

# 移除自选股
uv run python -m src.main unwatch <代码>

# 查看自选股列表
uv run python -m src.main watchlist
```

说明：
- 自选股不受全市场过滤器限制（不会被市值/成交额过滤掉）
- 自选股推送阈值默认 30 分（全市场是 60 分），轻微异动也会通知
- 自选股通知会标注 ⭐ 以区分全市场扫描的通知
- 支持设置目标价（到达后推送 🎯 提醒）和止损价（跌破后推送 🚨 预警）
- 午盘休市时（11:30-13:00）会推送自选股状态小结

## 通知格式示例

```
标题：🔴 正在快速拉升 · 兆易创新
正文：当前涨幅 +5.2% (603986)
     交易量是平时的 4.3 倍
     明显异动 (78分)
```

```
标题：⚠️ 涨停打开了 · XX科技
正文：当前涨幅 +9.8% (300xxx)
     交易量是平时的 6 倍（非常活跃）
     值得关注 (65分)
```

## 注意事项

1. 仅交易时间（09:25-15:05，工作日）自动扫描，非交易时间自动暂停
2. 数据来源为 AKShare（东方财富公开接口），个人研究用途
3. 所有推送均为 AI 信号参考，**不构成投资建议**
4. 每轮扫描需获取全市场 5800+ 只股票数据（58 页分页），实际耗时约 60-90 秒，因此真实轮询频率约为每 1-2 分钟一次
5. 如数据量异常骤降（疑似触发反爬），会自动暂停 5 分钟
