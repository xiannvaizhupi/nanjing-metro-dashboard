# 南京地铁客流数据可视化平台

一个纯静态的南京地铁客流数据看板，用于展示每日总客流、各线路客流、历史趋势，并结合天气、节假日和历史同期数据生成今日/明日客流预测。

## 功能概览

- 首页仪表盘：总客流、今日预测、明日预测、趋势图、线路占比弹窗、预测因素弹窗。
- 线路详情：按线路查看历史趋势、峰值、均值和线路对比。
- 历史数据：完整历史表格、日期筛选、CSV 导出、动态线路表头。
- 客流预测：独立岭回归模型根据星期、年内季节性、节假日、天气和滞后客流生成未来两天预测；旧规则仅在预测文件缺失时兜底。
- 预测评估：模型使用时间顺序留出集验证，并通过 `data/prediction_log.json` 持续记录到数后的预测误差。

## 当前数据

- 客流数据文件：`data/metro_data.json`
- 天气数据文件：`data/weather.json`
- 机器学习预测文件：`data/ml_predictions.json`
- 预测记录文件：`data/prediction_log.json`
- 客流数据范围：`2025-01-01` 至 `2026-07-23`
- 有效数据天数：566 天
- 最近更新：`2026-07-24`
- 已配置线路：14 条

已配置线路包括：

| 线路 | ID | 颜色 |
|---|---|---|
| 1号线 | L1 | `#009ACE` |
| 2号线 | L2 | `#A6093D` |
| 3号线 | L3 | `#009A44` |
| 4号线 | L4 | `#7D55C7` |
| 5号线 | L5 | `#F2DA51` |
| 7号线 | L7 | `#4A7729` |
| 10号线 | L10 | `#B9975B` |
| S1号线 | S1 | `#4BBBB4` |
| S2号线 | S2 | `#93282C` |
| S3号线 | S3 | `#BA84AC` |
| S6号线 | S6 | `#C98BDB` |
| S7号线 | S7 | `#B46B7A` |
| S8号线 | S8 | `#FF8000` |
| S9号线 | S9 | `#FFC600` |

## 本地运行

项目是纯静态站点，无需安装任何依赖，直接启动一个静态文件服务器即可：

```bash
python3 -m http.server 8080
```

然后访问：

```text
http://localhost:8080
```

或者使用任意其它静态服务器（例如 `npx serve`、VS Code Live Server 等）。

如果想本地预览一份仅含公开站点所需文件的精简副本（去除脚本与中间产物），可以先构建再起服务：

```bash
bash scripts/build-static.sh
python3 -m http.server 8080 -d dist
```

## 部署

项目是纯静态站点，可以直接托管在任意静态网站服务上，例如：

- **GitHub Pages**：把 `main` 分支（或 `dist/` 目录）作为发布源即可。
- **Vercel** / **Netlify** / **Cloudflare Pages** 等：识别为静态站点后无需构建命令，直接发布。
- 自有 Nginx / Apache：把仓库根目录或 `dist/` 挂到站点根目录。

构建脚本 `scripts/build-static.sh` 会生成 `dist/`，只复制公开站点需要的文件：

- `index.html`、`lines.html`、`history.html`
- `css/`
- `js/main.js`
- `Nanjing_Metro_Logo.svg.png`
- `data/metro_data.json`、`data/weather.json`、`data/ml_predictions.json`、`data/prediction_log.json`

如果你想用 Vercel 直接托管项目根目录，可以保留仓库里的 `vercel.json`，它把 `/data/*.json` 设置为 `Content-Type: application/json` 并允许跨域读取，便于前端 fetch。

## 数据更新

### 客流数据

客流数据由 `scripts/fetch_data.py` 维护。官网首页的客流数字由 JavaScript 动态加载，脚本会直接调用首页使用的官方 POST 接口获取昨日总量，再从首页嵌入的南京地铁官方微博组件获取各线路明细并交叉校验。若微博明细暂未发布，脚本先保存官网总量，后续自动补齐线路明细。脚本会更新：

- `data/metro_data.json`
- `data/prediction_log.json`
- `data/ml_predictions.json`

运行方式：

```bash
python3 scripts/fetch_data.py
```

`.github/workflows/update-metro-data.yml` 会在北京时间每天 09:30 和 11:30 自动执行，也可在 GitHub Actions 页面手动触发 `Update metro passenger flow`。每次任务最多重试三次：官网尚未发布或临时网络故障只记录提示并等待下一轮，不会产生失败邮件；解析器、数据完整性、预测文件或发布过程真正异常时才会失败。仅在数据发生变化时提交并推送 GitHub。

如需让 GitHub Actions 同步更新 Gitee，请在 GitHub 仓库的 Actions secrets 中配置 `GITEE_TOKEN`。未配置时任务仍会正常更新 GitHub，并明确记录跳过 Gitee；本地直接运行脚本时仍会使用本机凭据同步 `origin` 和 `gitee`。

在 CI 中脚本会通过 `METRO_SKIP_GIT=1` 跳过脚本内部的 Git 推送，改由工作流统一提交；本地直接运行脚本时仍保留原来的自动提交并推送到 `origin` 和 `gitee` 的行为。

### 机器学习预测

`scripts/ml_predictor.py` 是独立的数据预测模块，不依赖第三方机器学习包。它通过时间顺序验证选择岭回归参数和融合权重，结合星期、季节性、节假日、天气、短期同星期基线、去年同星期、前一日、前七日和近七日均值特征，输出模型参数、验证指标、预测区间和未来两天的预测值。停运日仍保留在历史数据与滞后特征中，但不作为常规回归训练目标，避免异常运营状态扭曲日常预测。

```bash
python3 scripts/ml_predictor.py
```

也可以指定预测天数或起始日期：

```bash
python3 scripts/ml_predictor.py --forecast-days 7 --start-date 2026-07-15
```

客流或天气更新完成后会自动重新生成 `data/ml_predictions.json`。首页优先读取该文件；若文件不存在、加载失败或当前日期不在输出范围内，才使用旧规则引擎临时预测。

### 天气数据

天气数据由 `update_weather.sh` 维护，脚本会调用 Open-Meteo 接口更新南京未来两天天气，并写入节假日标记。

运行方式：

```bash
./update_weather.sh
```

## 数据格式

`data/metro_data.json` 主要结构：

```json
{
  "metadata": {
    "last_updated": "2026-07-08",
    "lines": [
      {
        "id": "L1",
        "name": "1号线",
        "color": "#009ACE",
        "type": "main"
      }
    ]
  },
  "daily_data": [
    {
      "date": "2026-07-07",
      "total": 351.14,
      "is_weekend": false,
      "note": "",
      "lines": {
        "L1": 75.20,
        "L2": 63.10
      }
    }
  ],
  "statistics": {}
}
```

`data/weather.json` 是数组结构，每条记录包含日期、温度、天气、降水、节假日等字段。

## 项目结构

```text
nanjing-metro-dashboard/
├── index.html                 # 首页仪表盘
├── lines.html                 # 线路详情
├── history.html               # 历史数据
├── css/
│   ├── apple-style.css        # 当前页面主样式
│   ├── logo.css
│   └── style.css
├── js/
│   └── main.js                # 首页图表、预测和交互逻辑
├── data/
│   ├── metro_data.json        # 客流数据
│   ├── weather.json           # 天气与节假日数据
│   ├── ml_predictions.json    # 岭回归模型参数、验证指标与未来预测
│   ├── prediction_log.json    # 预测记录与评估
│   ├── raw_data.txt           # 原始抓取记录
│   └── 天气数据.txt           # 天气原始数据
├── scripts/
│   ├── build-static.sh        # 构建发布目录
│   ├── fetch_data.py          # 客流数据抓取与预测记录更新
│   ├── ml_predictor.py        # 独立机器学习预测模块
│   ├── test_fetch_data.py     # 解析器单元测试
│   └── test_ml_predictor.py   # 机器学习模块单元测试
├── update_weather.sh          # 天气数据更新脚本
├── vercel.json                # Vercel 静态部署配置（可选）
├── LINE_COLORS.md             # 线路配色说明
├── LICENSE
└── README.md
```

## 技术栈

- HTML / CSS / JavaScript
- Tailwind CDN
- ECharts CDN
- Python 标准库脚本
- Open-Meteo 天气接口

## 许可证

本项目使用 BSD 3-Clause License，完整条款见 `LICENSE`。
