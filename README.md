# 金油比日报

自动获取伦敦金现和布伦特原油价格，计算金油比并通过飞书推送日报。

## 功能特性

- 自动获取实时行情数据（TradingEconomics）
- 计算金油比并提供历史对照分析
- 通过飞书API推送精美卡片消息
- 支持定时执行和手动触发
- 完全免费，无需本地服务器

## 定时任务

| 时段 | 北京时间 | UTC 时间 | 运行日 |
|:-----|:---------|:---------|:-------|
| 亚盘收盘 | 15:00 | 07:00 | 周一至周五 |
| 美盘收盘 | 06:00 | 22:00 | 每天 |

## 部署方式

### 1. 配置 Secrets

在仓库的 **Settings** → **Secrets and variables** → **Actions** 中添加：

| Secret 名称 | 说明 |
|:------------|:-----|
| `FEISHU_APP_ID` | 飞书应用的 App ID |
| `FEISHU_APP_SECRET` | 飞书应用的 App Secret |

### 2. 手动触发测试

进入 **Actions** 标签页 → 选择 **金油比日报** → 点击 **Run workflow**

## 文件说明

- `gold_oil_ratio_daily.py` - 主程序脚本
- `requirements.txt` - Python 依赖
- `.github/workflows/daily-report.yml` - GitHub Actions 配置

## 注意事项

- 飞书凭证存储在 GitHub Secrets 中，不会泄露
- 代码中不包含任何敏感信息
- 公开仓库的 GitHub Actions 每月有 2000 分钟免费额度

## 免责声明

本工具仅供研究参考，不构成投资建议。
