# PulseRadar 飞书 Webhook 通知开发方案

## 1. 目标

在 PulseRadar 中增加飞书群机器人通知能力，让用户可以在手机/电脑端通过飞书实时接收自选股行情和异动信号。

适用场景：

- 跨设备接收：手机上随时查看行情播报，不必守在电脑前
- 跨平台部署：在服务器上运行 PulseRadar 时，桌面通知不可用，飞书成为主通知渠道
- 换电脑使用：无需重新配置桌面通知环境，群机器人一次配置持续可用
- 多人协作：团队共同关注同一组自选股，一个群聊统一接收

---

## 2. 飞书 Webhook 机器人原理

### 2.1 工作方式

飞书群聊支持添加「自定义机器人」，添加后会获得一个 Webhook URL，向该 URL 发送 HTTP POST 请求（Content-Type: application/json）即可将消息推送到群里。整个过程无需创建飞书应用、无需审批，创建即可用。

### 2.2 Webhook URL 格式

```
https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

### 2.3 支持的消息类型

| 类型 | msg_type | 说明 | 适用场景 |
|------|----------|------|----------|
| 纯文本 | text | 最简单，一段纯文字 | 快速通知、调试 |
| 富文本 | post | 支持多段落、加粗、超链接、@ 人 | 异动信号推送 |
| 消息卡片 | interactive | 支持复杂布局、多列、颜色标记、按钮 | 行情播报 |

### 2.4 签名校验（可选）

创建机器人时可开启「签名校验」，开启后每次请求需附带 timestamp 和 sign 字段，sign 的计算方式为：

```
签名字符串 = timestamp + "\n" + secret
sign = Base64(HMAC-SHA256(签名字符串, secret))
```

内部使用可以不开启签名校验，直接 POST 即可。

### 2.5 频率限制

飞书 Webhook 有频率限制，约为每分钟 100 条消息。PulseRadar 当前每 5 分钟播报一次行情 + 实时异动信号（通常每轮 0-3 条），完全在限制范围内。

---

## 3. 消息格式设计

### 3.1 行情播报（每 5 分钟一次）— 消息卡片

使用飞书消息卡片（interactive），信息密度高，手机端展示效果好。

**视觉效果：**

```
┌─────────────────────────────────────┐
│ ⭐ 自选股行情 · 14:35               │
├─────────────────────────────────────┤
│ 兆易创新  +3.52%  ¥98.50           │
│ 量比 2.1 | 换手 4.3% | 成交 8.2亿  │
│ 🟢 多维共振，可考虑介入              │
│                                     │
│ 盛新锂能  -1.20%  ¥25.80           │
│ 量比 0.9 | 换手 1.8% | 成交 2.1亿  │
│ ⚪ 信号中性，暂无明确方向             │
│                                     │
│ ...                                 │
├─────────────────────────────────────┤
│ 📊 数据来源: 腾讯财经 · 14:35 刷新  │
└─────────────────────────────────────┘
```

**完整卡片 JSON 模板：**

```json
{
  "msg_type": "interactive",
  "card": {
    "header": {
      "title": {
        "tag": "plain_text",
        "content": "⭐ 自选股行情 · 14:35"
      },
      "template": "blue"
    },
    "elements": [
      {
        "tag": "div",
        "text": {
          "tag": "lark_md",
          "content": "**兆易创新**  <font color='red'>+3.52%</font>  ¥98.50\n量比 2.1 | 换手 4.3% | 成交 8.2亿\n🟢 多维共振，可考虑介入"
        }
      },
      {
        "tag": "hr"
      },
      {
        "tag": "div",
        "text": {
          "tag": "lark_md",
          "content": "**盛新锂能**  <font color='green'>-1.20%</font>  ¥25.80\n量比 0.9 | 换手 1.8% | 成交 2.1亿\n⚪ 信号中性，暂无明确方向"
        }
      },
      {
        "tag": "hr"
      },
      {
        "tag": "note",
        "elements": [
          {
            "tag": "plain_text",
            "content": "📊 数据来源: 腾讯财经 · 14:35 刷新"
          }
        ]
      }
    ]
  }
}
```

### 3.2 异动信号（实时触发）— 富文本

异动信号需要快速传达关键信息，使用富文本（post）格式，支持加粗和多行。

**视觉效果：**

```
🔴 正在快速拉升 · 兆易创新

当前涨幅 +5.2% (603986)
交易量是平时的 3.5 倍
涨速 +2.8%/min 正在加速
明显异动 (75分)
```

**完整 post JSON 模板：**

```json
{
  "msg_type": "post",
  "content": {
    "post": {
      "zh_cn": {
        "title": "🔴 正在快速拉升 · 兆易创新",
        "content": [
          [
            {
              "tag": "text",
              "text": "当前涨幅 "
            },
            {
              "tag": "text",
              "text": "+5.2%",
              "style": ["bold"]
            },
            {
              "tag": "text",
              "text": " (603986)"
            }
          ],
          [
            {
              "tag": "text",
              "text": "交易量是平时的 3.5 倍（非常活跃）"
            }
          ],
          [
            {
              "tag": "text",
              "text": "涨速 +2.8%/min 正在加速"
            }
          ],
          [
            {
              "tag": "text",
              "text": "明显异动 (75分)"
            }
          ]
        ]
      }
    }
  }
}
```

---

## 4. 代码改动方案

### 4.1 `notifier.py` — 新增飞书发送函数

在现有 `send_daxiang_notification` 函数之后，新增以下三个函数：

```python
import hashlib
import hmac
import base64


def _build_feishu_sign(secret: str, timestamp: str) -> str:
    """
    计算飞书 Webhook 签名。
    
    参数:
        secret: 机器人的签名密钥
        timestamp: 当前时间戳（秒级字符串）
    
    返回:
        Base64 编码的 HMAC-SHA256 签名
    """
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def send_feishu_notification(title: str, message: str, config: dict, msg_type: str = "text") -> bool:
    """
    通过飞书 Webhook 发送通知。
    
    参数:
        title: 消息标题（用于 text/post 类型）
        message: 消息正文
        config: 全局配置字典（从中读取 feishu_config）
        msg_type: 消息类型 (text/post)
    
    返回:
        是否发送成功
    """
    import requests
    
    feishu_config = config.get("notifications", {}).get("feishu_config", {})
    webhook_url = feishu_config.get("webhook_url", "")
    
    if not webhook_url:
        logger.debug("飞书 Webhook URL 未配置，跳过")
        return False
    
    # 构建请求体
    if msg_type == "text":
        payload = {
            "msg_type": "text",
            "content": {
                "text": f"【PulseRadar】{title}\n{message}"
            }
        }
    elif msg_type == "post":
        # 将 message 按行拆分为富文本段落
        lines = message.split("\n")
        content_lines = []
        for line in lines:
            content_lines.append([{"tag": "text", "text": line}])
        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": f"【PulseRadar】{title}",
                        "content": content_lines
                    }
                }
            }
        }
    else:
        logger.warning(f"不支持的飞书消息类型: {msg_type}")
        return False
    
    # 签名（如果配置了 secret）
    secret = feishu_config.get("secret", "")
    if secret:
        timestamp = str(int(time.time()))
        sign = _build_feishu_sign(secret, timestamp)
        payload["timestamp"] = timestamp
        payload["sign"] = sign
    
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        result = resp.json()
        if result.get("code") == 0:
            logger.debug(f"飞书通知已发送: {title}")
            return True
        else:
            logger.warning(f"飞书通知发送失败: {result.get('msg', '未知错误')}")
            return False
    except requests.Timeout:
        logger.warning("飞书通知发送超时")
        return False
    except Exception as e:
        logger.error(f"飞书通知发送异常: {e}")
        return False


def send_feishu_card(card_data: dict, config: dict) -> bool:
    """
    通过飞书 Webhook 发送消息卡片。
    
    参数:
        card_data: 完整的消息卡片数据（含 header + elements）
        config: 全局配置字典
    
    返回:
        是否发送成功
    """
    import requests
    
    feishu_config = config.get("notifications", {}).get("feishu_config", {})
    webhook_url = feishu_config.get("webhook_url", "")
    
    if not webhook_url:
        logger.debug("飞书 Webhook URL 未配置，跳过")
        return False
    
    payload = {
        "msg_type": "interactive",
        "card": card_data
    }
    
    # 签名
    secret = feishu_config.get("secret", "")
    if secret:
        timestamp = str(int(time.time()))
        sign = _build_feishu_sign(secret, timestamp)
        payload["timestamp"] = timestamp
        payload["sign"] = sign
    
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        result = resp.json()
        if result.get("code") == 0:
            logger.debug("飞书消息卡片已发送")
            return True
        else:
            logger.warning(f"飞书卡片发送失败: {result.get('msg', '未知错误')}")
            return False
    except requests.Timeout:
        logger.warning("飞书卡片发送超时")
        return False
    except Exception as e:
        logger.error(f"飞书卡片发送异常: {e}")
        return False
```

### 4.2 `watchlist_report.py` — 新增飞书版行情播报

在现有 `push_watchlist_report` 函数之后，新增飞书版播报函数：

```python
from .notifier import send_feishu_card


def push_watchlist_report_feishu(reports: list[dict], config: dict):
    """
    将自选股行情快照通过飞书消息卡片推送。
    所有股票汇总在一张卡片中，信息密度高。
    
    参数:
        reports: generate_watchlist_report 返回的行情数据列表
        config: 全局配置字典
    """
    if not reports:
        return
    
    now_str = datetime.now().strftime("%H:%M")
    
    # 构建卡片 elements
    elements = []
    
    for i, r in enumerate(reports):
        name = r["name"]
        price = r["price"]
        change_pct = r["change_pct"]
        volume_ratio = r["volume_ratio"]
        turnover_rate = r["turnover_rate"]
        turnover = r["turnover"]
        analysis = r["analysis"]
        
        # 涨跌颜色
        sign = "+" if change_pct > 0 else ""
        if change_pct > 0:
            color_tag = f"<font color='red'>{sign}{change_pct:.2f}%</font>"
        elif change_pct < 0:
            color_tag = f"<font color='green'>{change_pct:.2f}%</font>"
        else:
            color_tag = f"{change_pct:.2f}%"
        
        # 成交额格式化
        turnover_str = _format_amount(turnover)
        
        # 买点分析结论
        verdict = analysis["verdict"]
        
        content = (
            f"**{name}**  {color_tag}  ¥{price:.2f}\n"
            f"量比 {volume_ratio:.1f} | 换手 {turnover_rate:.1f}% | 成交 {turnover_str}\n"
            f"{verdict}"
        )
        
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": content
            }
        })
        
        # 每只股票之间加分割线（最后一只不加）
        if i < len(reports) - 1:
            elements.append({"tag": "hr"})
    
    # 底部备注
    elements.append({
        "tag": "note",
        "elements": [
            {
                "tag": "plain_text",
                "content": f"📊 数据来源: 腾讯财经 · {now_str} 刷新"
            }
        ]
    })
    
    # 组装卡片
    card_data = {
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"⭐ 自选股行情 · {now_str}"
            },
            "template": "blue"
        },
        "elements": elements
    }
    
    send_feishu_card(card_data, config)
```

### 4.3 `config.json` — 新增配置项

在 `notifications` 对象中新增飞书相关配置：

```json
{
  "notifications": {
    "desktop": true,
    "daxiang": false,
    "feishu": true,
    "feishu_config": {
      "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "secret": "",
      "enable_card": true
    },
    "email_summary": false,
    "sound": true
  }
}
```

**配置项说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `feishu` | bool | 是否启用飞书推送 |
| `feishu_config.webhook_url` | string | 飞书群机器人的 Webhook URL |
| `feishu_config.secret` | string | 签名密钥（留空则不启用签名校验） |
| `feishu_config.enable_card` | bool | 行情播报是否使用消息卡片（false 则降级为纯文本） |

### 4.4 `scanner.py` — 集成飞书推送

#### 4.4.1 新增 import

在文件头部 import 区域修改：

```python
from .watchlist_report import generate_watchlist_report, push_watchlist_report, push_watchlist_report_feishu
from .notifier import notify_signal, send_desktop_notification, send_feishu_notification
```

#### 4.4.2 修改 `scan_once` 方法

在行情播报逻辑中增加飞书推送调用（约第 348 行附近）：

```python
# 2. 行情播报（按 watchlist_report_interval 间隔）
now_ts = time.time()
if now_ts - self._last_watchlist_report_time >= self._watchlist_report_interval:
    watch_codes = self.watchlist_mgr.get_stock_codes()
    if watch_codes:
        try:
            reports = generate_watchlist_report(df, watch_codes)
            if reports:
                push_watchlist_report(reports)
                # >>> 新增：飞书行情播报 <<<
                if self.config.get("notifications", {}).get("feishu", False):
                    push_watchlist_report_feishu(reports, self.config)
                self._last_watchlist_report_time = now_ts
                summaries = []
                for r in reports:
                    sign = "+" if r["change_pct"] > 0 else ""
                    summaries.append(f"{r['name']} {sign}{r['change_pct']:.2f}%")
                logger.info(f"自选股播报: {', '.join(summaries)}")
        except Exception as e:
            logger.warning(f"自选股播报失败: {e}")
```

#### 4.4.3 修改 `notifier.py` 中的 `notify_signal` 函数

在现有的通知渠道列表中增加飞书推送（在大象推送之后）：

```python
def notify_signal(signal: dict, config: dict) -> bool:
    # ... 现有代码保持不变 ...
    
    # 1. 桌面通知
    if notifications.get("desktop", True):
        notify_type = "warning" if score >= 80 else "info"
        if send_desktop_notification(title, message, notify_type):
            notified = True
    
    # 2. 大象消息推送
    if notifications.get("daxiang", False):
        send_daxiang_notification(title, message, config)
    
    # 3. 飞书消息推送（新增）
    if notifications.get("feishu", False):
        send_feishu_notification(title, message, config, msg_type="post")
    
    # 4. 通知声音
    if notifications.get("sound", False) and notified:
        is_urgent = score >= 90 or signal.get("signal_type") in ("止损预警", "目标价到达")
        play_alert_sound(urgent=is_urgent)
    
    if notified:
        mark_notified(stock_code)
    
    return notified
```

---

## 5. 开发步骤

### Step 1：创建飞书测试群 + 添加自定义机器人

1. 在飞书中创建一个测试群（可以只有自己一人）
2. 群设置 → 群机器人 → 添加机器人 → 自定义机器人
3. 填写名称（如 "PulseRadar 行情播报"）、描述
4. 复制生成的 Webhook URL
5. 签名校验：内部测试可以不开，生产环境建议开启
6. 将 Webhook URL 填入 `config.json` 的 `feishu_config.webhook_url`

### Step 2：实现 `send_feishu_notification` 基础函数并测试

1. 在 `notifier.py` 中新增 `_build_feishu_sign`、`send_feishu_notification`、`send_feishu_card` 三个函数
2. 在文件头部新增 `import hashlib, hmac, base64`
3. 编写简单的测试脚本验证基础发送：

```python
# test_feishu.py（临时测试，验证后删除）
import sys
sys.path.insert(0, ".")
from src.notifier import send_feishu_notification

config = {
    "notifications": {
        "feishu": True,
        "feishu_config": {
            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/your-token-here",
            "secret": ""
        }
    }
}

result = send_feishu_notification("测试通知", "PulseRadar 飞书通知测试成功！", config)
print(f"发送结果: {result}")
```

4. 运行测试脚本，确认群里收到消息

### Step 3：实现消息卡片模板

1. 在 `watchlist_report.py` 中新增 `push_watchlist_report_feishu` 函数
2. 新增 import：`from .notifier import send_feishu_card`
3. 可使用飞书消息卡片搭建工具预览效果：https://open.feishu.cn/tool/cardbuilder
4. 测试卡片发送：

```python
# test_feishu_card.py（临时测试，验证后删除）
import sys
sys.path.insert(0, ".")
from src.watchlist_report import push_watchlist_report_feishu

config = {
    "notifications": {
        "feishu": True,
        "feishu_config": {
            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/your-token-here",
            "secret": "",
            "enable_card": True
        }
    }
}

test_reports = [
    {
        "name": "兆易创新", "code": "603986", "price": 98.5,
        "change_pct": 3.52, "volume_ratio": 2.1, "turnover_rate": 4.3,
        "turnover": 820000000, "volume": 85000, "high": 99.0, "low": 95.0,
        "speed": 1.2,
        "analysis": {"verdict": "🟢 多维共振，可考虑介入", "score": 5,
                     "reasons": ["涨幅温和", "量比放大"], "cautions": []}
    },
    {
        "name": "盛新锂能", "code": "002240", "price": 25.8,
        "change_pct": -1.2, "volume_ratio": 0.9, "turnover_rate": 1.8,
        "turnover": 210000000, "volume": 42000, "high": 26.5, "low": 25.5,
        "speed": -0.3,
        "analysis": {"verdict": "⚪ 信号中性，暂无明确方向", "score": 0,
                     "reasons": [], "cautions": ["量比缩量"]}
    }
]

push_watchlist_report_feishu(test_reports, config)
print("卡片发送完成，请查看飞书群")
```

### Step 4：集成到 scanner 主流程

1. 修改 `scanner.py` 的 import 语句
2. 在 `scan_once` 的行情播报逻辑中加入飞书推送
3. 修改 `notifier.py` 的 `notify_signal` 函数，加入飞书渠道
4. 更新 `config.json`，确保新配置项有默认值

### Step 5：测试完整流程

1. 配置好 `config.json` 中的飞书参数
2. 启动 PulseRadar（交易时间内）
3. 验证：
   - 每 5 分钟收到一次行情卡片
   - 自选股触发异动时收到富文本信号通知
   - 手机端飞书 App 能正常收到推送
   - 桌面通知和飞书通知同时工作互不影响
4. 验证降级：webhook_url 为空或无效时不影响其他通知渠道

### 预估工时

| 步骤 | 预估时间 |
|------|----------|
| Step 1: 创建机器人 | 5 分钟 |
| Step 2: 基础发送函数 | 20 分钟 |
| Step 3: 消息卡片模板 | 30 分钟 |
| Step 4: 集成主流程 | 15 分钟 |
| Step 5: 测试验证 | 20 分钟 |
| **合计** | **约 1.5 小时** |

---

## 6. 注意事项

### 6.1 频率限制

飞书 Webhook 每分钟约 100 条消息限制。PulseRadar 当前每 5 分钟播报一次行情（1 条卡片），加上偶发的异动信号（通常 0-5 条/轮），远低于限制。但如果未来扩展为全市场扫描，需要加入消息合并逻辑。

### 6.2 安全性

Webhook URL 中包含 token，泄露后任何人都可以向群里发消息。安全建议：

- 不要将 `config.json` 中的 webhook_url 提交到 git
- 在 `.gitignore` 中添加 `config.json`（或使用 `config.local.json` 覆盖）
- 推荐通过环境变量传入：`export PULSE_RADAR_FEISHU_WEBHOOK="https://..."`
- 代码中加入环境变量读取的降级逻辑：

```python
webhook_url = feishu_config.get("webhook_url") or os.environ.get("PULSE_RADAR_FEISHU_WEBHOOK", "")
```

### 6.3 签名校验

签名校验是可选的。内部个人使用可以不开（减少配置复杂度），团队共享使用建议开启，防止 URL 泄露后被滥用。

### 6.4 消息卡片兼容性

消息卡片在飞书手机端展示效果最好，支持红绿颜色标记、分割线、多行排版。但需注意：

- `<font color='red'>` 标签在旧版飞书客户端可能不渲染颜色
- 卡片总长度有限制（约 30KB），自选股数量较多时（>20 只）需要分批发送
- 如果 `enable_card` 设为 false，可降级为纯文本格式播报

### 6.5 错误处理

飞书推送失败不应影响主扫描流程。当前设计中所有飞书发送函数都有完整的异常处理，失败只记录日志不中断程序。网络超时设为 10 秒，避免阻塞扫描循环。

### 6.6 与现有通知渠道的关系

飞书通知是独立的渠道，与桌面通知（catdesk notify）、大象消息互不影响。可以同时开启多个渠道，也可以只开飞书（适合服务器部署场景）。通知去重机制（5 分钟冷却）对所有渠道统一生效。
