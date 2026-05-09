# 金油比日报

自动获取伦敦金现和布伦特原油价格，计算金油比并通过飞书推送精美卡片日报。

## 功能特性

- 自动获取实时行情数据（TradingEconomics）
- 计算金油比并提供 5 级水平判定（偏低/适中/偏高/极高/极端）
- 📊 **数据对比**：昨日、近 7 天、近 1 月、近 1 季涨跌幅
- 时段分离存储：亚盘收盘和美盘收盘独立记录，互不覆盖
- 通过飞书官方 API 推送 Interactive 卡片消息（含颜色动态标识）
- 卡片推送失败时自动降级为纯文本消息
- 支持定时执行和手动触发
- 完全免费，无需本地服务器（基于 GitHub Actions）

## 什么是金油比？

**金油比（Gold-to-Oil Ratio）** = 伦敦金现价格 ÷ 布伦特原油价格

金油比是衡量市场风险情绪的重要指标，基于 1970 年至今的历史数据：

| 金油比 | 判定 | 含义 | 历史案例 |
|:-------|:-----|:-----|:---------|
| < 10 | 偏低 | 经济过热或通胀预期强，原油需求旺盛 | 2005 年、2008 年初 |
| 10 ~ 25 | 适中 | 经济运行相对稳定，历史常态区间 | 1970 年以来大部分时期 |
| 25 ~ 35 | 偏高 | 市场避险情绪升温，需关注经济下行风险 | 2008 金融危机(26) |
| 35 ~ 50 | 极高 | 通常预示重大危机，经济衰退风险显著增加 | 1973 原油危机(41) |
| > 50 | 极端 | 市场严重分化，历史罕见危机信号 | 2020 疫情(100+)、2025 关税冲突(50+) |

> 历史经验：金油比突破 25 通常预示危机，超过 35 则预示重大危机。

## 工作流程

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  GitHub     │     │  获取实时    │     │  保存数据    │     │  计算金油比 │     │  飞书 API   │
│  Actions    │────▶│  行情数据    │────▶│  (时段分离)  │────▶│  生成日报   │────▶│  推送卡片   │
│  定时触发   │     │  (TE 爬取)   │     │  (JSON持久)  │     │  (含数据对比)│    │  消息通知   │
└─────────────┘     └──────────────┘     └──────────────┘     └─────────────┘     └─────────────┘
```

### 执行步骤

1. **GitHub Actions** 按 cron 定时触发（或手动触发）
2. 爬取 [TradingEconomics](https://zh.tradingeconomics.com/commodity/gold) 获取伦敦金现和布伦特原油实时价格
3. 按时段（亚盘收盘/美盘收盘）保存数据到 JSON 文件
4. 计算金油比，结合历史常态区间（10:1~25:1）进行 5 级水平判定
5. 计算多维度数据对比涨跌幅（同类型时段对比）
6. 通过飞书官方 API 发送 Interactive 卡片消息（失败时降级为纯文本）

## 定时任务

| 时段 | 北京时间 | UTC 时间 | 运行日 |
|:-----|:---------|:---------|:-------|
| 亚盘收盘 | 15:05 | 07:05 | 周一至周五 |
| 美盘收盘 | 06:05 | 22:05 | 每天 |

> ⏰ 定时任务错开整点 5 分钟触发，以减少 GitHub Actions 排队延迟。

## 部署方式

### 1. 创建飞书应用

1. 打开 [飞书开放平台](https://open.feishu.cn/)，登录并创建一个**企业自建应用**
2. 在 **权限管理** 中开通以下权限：

| 权限 | 权限标识 | 用途 |
|:-----|:---------|:-----|
| 获取用户基本信息 | `contact:user.base:readonly` | 查找推送目标用户 |
| 获取与发送单聊消息 | `im:message:send_as_bot` | 发送卡片/文本消息 |

3. 在 **版本管理与发布** 中发布应用版本，并联系管理员审批

### 2. 配置 GitHub Secrets

在仓库的 **Settings** → **Secrets and variables** → **Actions** 中添加：

| Secret 名称 | 说明 | 获取方式 |
|:------------|:-----|:---------|
| `FEISHU_APP_ID` | 飞书应用的 App ID | 飞书开放平台 → 应用凭证 |
| `FEISHU_APP_SECRET` | 飞书应用的 App Secret | 飞书开放平台 → 应用凭证 |
| `DATA_ENCRYPT_KEY` | 数据加密密钥 | 自定义一个强密码（建议 16 位以上随机字符串） |
| `PUSH_TOKEN` | Git 推送 Token | GitHub Settings → Developer settings → Personal access tokens → 勾选 `repo` 权限 |

> ⚠️ 凭证存储在 GitHub Secrets 中，不会泄露。代码中不包含任何敏感信息。
> 
> **首次部署必须配置 `DATA_ENCRYPT_KEY` 和 `PUSH_TOKEN`**，否则 Actions 无法持久化数据。

### 3. 手动触发测试

进入 **Actions** 标签页 → 选择 **金油比日报** → 点击 **Run workflow**

### 4. 验证推送

检查飞书是否收到金油比日报卡片消息。如果未收到，请参考下方 [常见问题](#常见问题) 排查。

## 本地开发

### 环境要求

- Python 3.10+
- `requests` 库

### 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/BenHPM/gold-oil-ratio-daily.git
cd gold-oil-ratio-daily

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置飞书凭证（本地调试用）
export FEISHU_APP_ID="your_app_id"
export FEISHU_APP_SECRET="your_app_secret"

# 4. 运行（自动判断时段）
python gold_oil_ratio_daily.py

# 5. 手动指定时段测试
python gold_oil_ratio_daily.py --session 亚盘收盘
python gold_oil_ratio_daily.py --session 美盘收盘
```

### 时段判断规则

| 北京时间 | 自动归属时段 |
|:---------|:-------------|
| 06:00 - 14:59 | 美盘收盘 |
| 15:00 - 05:59 | 亚盘收盘 |

> 定时任务以外的时间测试时，可通过 `--session` 参数手动指定时段。

## 文件说明

```
gold-oil-ratio-daily/
├── .github/
│   └── workflows/
│       └── daily-report.yml      # GitHub Actions 定时任务配置
├── gold_oil_ratio_daily.py       # 主程序脚本（数据获取 + 卡片生成 + 飞书推送）
├── data_store.py                 # 数据存储模块（加密持久化 + 多维度对比计算）
├── gold_oil_data.enc             # 加密数据文件（自动生成，提交到仓库）
├── gold_oil_data.json            # 明文数据文件（本地开发用，已加入 .gitignore）
├── requirements.txt              # Python 依赖（requests）
├── .gitignore                    # Git 忽略规则
└── README.md                     # 项目文档
```

### 核心模块说明

| 模块/函数 | 功能 |
|:---------|:-----|
| `fetch_gold_price()` | 爬取 TradingEconomics 获取伦敦金现价格和涨跌幅 |
| `fetch_brent_oil_price()` | 爬取 TradingEconomics 获取布伦特原油价格和涨跌幅 |
| `calculate_ratio()` | 计算金油比（黄金价格 ÷ 原油价格） |
| `get_current_session()` | 根据北京时间自动判断当前时段（亚盘收盘/美盘收盘） |
| `generate_report()` | 生成飞书 Interactive 卡片 JSON 和纯文本降级内容 |
| `FeishuPusher` | 飞书消息推送器，支持卡片消息和纯文本消息，含重试机制 |
| `add_record()` | 按日期+时段存储金油比数据，同一天不同时段独立记录 |
| `get_multi_period_changes()` | 计算多维度数据对比涨跌幅（同类型时段对比） |

### 数据存储说明

数据按 **日期 + 时段** 分离存储，同一天可保留亚盘收盘和美盘收盘两条记录。

**存储方式**：
- **GitHub Actions 环境**：加密存储为 `gold_oil_data.enc`，每次运行后自动提交到仓库
- **本地开发环境**：明文存储为 `gold_oil_data.json`（通过环境变量 `DATA_ENCRYPT_KEY` 切换）

**加密机制**：
- 使用 PBKDF2 + XOR + Base64 加密，密钥存储在 GitHub Secrets 中
- 仓库中的 `.enc` 文件为加密后的乱码，他人无法读取
- 本地开发时设置 `DATA_ENCRYPT_KEY` 环境变量即可解密

```bash
# 本地解密查看数据
export DATA_ENCRYPT_KEY="your_encrypt_key"
python -c "
from data_store import load_data
import json
print(json.dumps(load_data(), ensure_ascii=False, indent=2))
"
```

- 同一日期 + 同一时段多次运行会**更新**，不会重复
- 自动保留最近 240 条记录（约 4 个月）
- `gold_oil_data.json` 已加入 `.gitignore`，不会提交明文数据

### 数据对比维度

| 对比维度 | 说明 | 数据积累时间 |
|:---------|:-----|:-----------|
| 昨日 | 与昨天同类型时段对比 | 第 2 天 |
| 近 7 天 | 与近 7 天同类型时段平均值对比 | 第 7 天 |
| 近 1 月 | 与近 30 天同类型时段平均值对比 | 第 30 天 |
| 近 1 季 | 与近 90 天同类型时段平均值对比 | 第 90 天 |

> **对比逻辑**：亚盘收盘只对比亚盘收盘数据，美盘收盘只对比美盘收盘数据，避免跨时段比较导致偏差。

## 常见问题

### Q: 推送失败，提示"飞书凭证未配置"

请确认已在 GitHub Secrets 中正确配置 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET`，且没有拼写错误。

### Q: 推送失败，提示"未找到用户"

`find_user()` 方法默认获取通讯录中的第一个用户。如果你的飞书应用没有可见的通讯录权限，或企业内没有其他成员，可能无法找到用户。可以修改 `find_user()` 方法，指定特定的 `user_id` 来精准推送。

### Q: 数据获取失败

TradingEconomics 可能会更新页面结构，导致正则匹配失败。此时需要检查并更新 `fetch_gold_price()` 和 `fetch_brent_oil_price()` 中的匹配规则。

### Q: 数据对比显示 ❓ --

数据对比需要积累一定量的历史记录。首次部署后，各维度的可用时间：
- **昨日**：第 2 天即可显示
- **近 7 天**：第 7 天后
- **近 1 月**：第 30 天后
- **近 1 季**：第 90 天后

### Q: 公开仓库的 Actions 额度够用吗？

GitHub 对公开仓库提供每月 **2000 分钟** 的免费 Actions 额度。本任务每次运行约 30 秒，每日 2 次，每月约 20 分钟，远低于免费额度。

## 技术栈

| 技术 | 用途 |
|:-----|:-----|
| Python 3.12 | 主程序语言 |
| requests | HTTP 请求（数据爬取 + 飞书 API） |
| JSON | 本地数据持久化（时段分离存储） |
| GitHub Actions | 定时任务调度 |
| 飞书开放平台 API | Interactive 卡片消息推送 |

## 免责声明

本工具仅供研究参考，不构成投资建议。金油比分析基于历史数据和公开信息，实际市场情况请以专业机构分析为准。

## License

MIT
