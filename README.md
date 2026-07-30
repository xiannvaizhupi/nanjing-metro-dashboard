# 南京地铁客流数据可视化平台

一个纯静态的南京地铁客流数据看板，用于展示每日总客流、各线路客流、历史趋势，并结合天气、节假日和历史同期数据生成今日/明日客流预测。

完整的数据链路、存储结构、机器学习算法、当前模型参数和风险分析见 [项目技术报告](docs/project-technical-report.md)。

## 功能概览

- 首页仪表盘：总客流、今日预测、明日预测、趋势图、线路占比弹窗、预测因素弹窗。
- 线路详情：按线路查看历史趋势、峰值、均值、线路对比和独立模型未来两天预测。
- 历史数据：完整历史表格、日期筛选、CSV 导出、动态线路表头。
- 客流预测：线网总量和 14 条线路分别训练独立时间序列模型，根据滚动验证自动选择训练窗口、岭回归参数和同星期基线融合策略；旧规则仅在预测文件缺失时兜底。
- 预测评估：模型使用时间顺序留出集验证，并通过 `data/prediction_log.json` 持续记录到数后的预测误差。

## 当前数据

- 客流数据文件：`data/metro_data.json`
- 天气数据文件：`data/weather.json`
- 机器学习预测文件：`data/ml_predictions.json`
- 预测记录文件：`data/prediction_log.json`
- 客流数据范围：`2025-01-01` 至 `2026-07-28`
- 有效数据天数：571 天
- 最近更新：`2026-07-29`
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

`.github/workflows/update-metro-data.yml` 会在北京时间每天 09:47 至 21:47 每小时错峰检查一次，也可在 GitHub Actions 页面手动触发 `Update metro passenger flow`。官网尚未发布时任务会立即正常结束并等待下一轮；临时网络故障最多重试三次。上述情况不会产生失败邮件，只有解析器、数据完整性、预测文件或发布过程真正异常时才会失败。仅在数据发生变化时提交并推送 GitHub。

如需让 GitHub Actions 同步更新 Gitee，请在 GitHub 仓库的 Actions secrets 中配置 `GITEE_TOKEN`。未配置时任务仍会正常更新 GitHub，并明确记录跳过 Gitee；本地直接运行脚本时仍会使用本机凭据同步 `origin` 和 `gitee`。

在 CI 中脚本会通过 `METRO_SKIP_GIT=1` 跳过脚本内部的 Git 推送，改由工作流统一提交；本地直接运行脚本时仍保留原来的自动提交并推送到 `origin` 和 `gitee` 的行为。

### 机器学习预测

`scripts/ml_predictor.py` 是独立的数据预测模块，不依赖第三方机器学习包。线网总量与每条线路分别使用自身历史数据训练，候选策略包括岭回归、最近 4 个同星期算术均值、近期加权同星期基线及其融合模型。模块通过滚动时间验证为每个序列独立选择近 180 天、365 天或全部历史训练窗口，以及岭回归参数、基线类型和融合权重。

模型特征包括星期、年内季节性、节假日、天气、去年同星期、前一日、前七日、近七日均值和近期同星期客流。新开通且样本较少的线路会自动使用小样本季节基线，不会强行拟合高维回归。各线路完成独立预测后再按线网总预测执行分层校准，保证线路预测合计与线网总量严格一致。输出文件同时记录每条线路的策略、训练范围、验证 MAE/RMSE/MAPE、预测区间和未来两天预测值。

停运日保留在历史滞后特征中，但线网停运日不作为总量常规训练目标；单条线路停运只从对应线路训练目标中排除，避免影响其他正常运营线路。

```bash
python3 scripts/ml_predictor.py
```

也可以指定预测天数或起始日期：

```bash
python3 scripts/ml_predictor.py --forecast-days 7 --start-date 2026-07-15
```

客流或天气更新完成后会自动重新生成 `data/ml_predictions.json`。首页优先读取该文件；若文件不存在、加载失败或当前日期不在输出范围内，才使用旧规则引擎临时预测。

### 天气数据

天气数据由独立模块 `scripts/update_weather.py` 维护，根目录的 `update_weather.sh` 是便捷入口。模块只使用 Python 标准库，通过 HTTPS 调用 Open-Meteo，默认回补最近 14 天并维护未来 7 天天气，修正天气类型和国务院公布的 2025—2026 年节假日标记，再重新训练机器学习预测。

`.github/workflows/update-weather.yml` 会在北京时间每天 08:17 自动更新天气；它与客流工作流共用写入并发锁，避免两个任务同时改写 `data/ml_predictions.json`。Open-Meteo 暂时不可用时任务记录警告并等待次日重试，数据格式或模型校验失败时才会报错。

运行方式：

```bash
./update_weather.sh
# 等价于：python3 scripts/update_weather.py
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
│   ├── ml_predictions.json    # 线网及各线路模型、验证指标与未来预测
│   ├── prediction_log.json    # 预测记录与评估
│   ├── raw_data.txt           # 原始抓取记录
│   └── 天气数据.txt           # 天气原始数据
├── scripts/
│   ├── build-static.sh        # 构建发布目录
│   ├── fetch_data.py          # 客流数据抓取与预测记录更新
│   ├── ml_predictor.py        # 独立机器学习预测模块
│   ├── update_weather.py      # 独立天气更新与预测重训模块
│   ├── test_fetch_data.py     # 解析器单元测试
│   ├── test_ml_predictor.py   # 机器学习模块单元测试
│   └── test_update_weather.py # 天气更新模块单元测试
├── update_weather.sh          # 可移植天气更新入口
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
