# 南京地铁客流数据可视化平台

一个纯静态的南京地铁客流数据看板，用于展示每日总客流、各线路客流、历史趋势，并结合天气、节假日和历史同期数据生成今日/明日客流预测。

当前项目已支持 EdgeOne Pages 静态部署，也保留了 Vercel 配置。

## 功能概览

- 首页仪表盘：总客流、今日预测、明日预测、趋势图、线路占比弹窗、预测因素弹窗。
- 线路详情：按线路查看历史趋势、峰值、均值和线路对比。
- 历史数据：完整历史表格、日期筛选、CSV 导出、动态线路表头。
- 客流预测：基于历史同星期数据、节假日系数、天气和近期趋势进行前端预测。
- 预测评估：通过 `data/prediction_log.json` 展示预测误差统计。
- 静态部署：通过 `edgeone.json` 和 `scripts/build-static.sh` 输出可发布的 `dist/` 目录。

## 当前数据

- 客流数据文件：`data/metro_data.json`
- 天气数据文件：`data/weather.json`
- 预测记录文件：`data/prediction_log.json`
- 客流数据范围：`2025-01-01` 至 `2026-04-23`
- 数据天数：478 天
- 最近更新：`2026-04-24`
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

项目无需安装前端依赖，直接启动静态服务器即可。

```bash
python3 -m http.server 8080
```

然后访问：

```text
http://localhost:8080
```

## 构建发布目录

EdgeOne Pages 部署时会运行：

```bash
bash scripts/build-static.sh
```

脚本会生成 `dist/`，只复制公开网站需要的文件：

- `index.html`
- `lines.html`
- `history.html`
- `css/`
- `js/main.js`
- `Nanjing_Metro_Logo.svg.png`
- `data/metro_data.json`
- `data/weather.json`
- `data/prediction_log.json`

本地预览发布产物：

```bash
bash scripts/build-static.sh
python3 -m http.server 8080 -d dist
```

## EdgeOne Pages 部署

项目根目录已包含 `edgeone.json`：

```text
构建命令：bash scripts/build-static.sh
输出目录：./dist
```

部署步骤：

1. 将项目推送到 Git 仓库，例如 Gitee 或 GitHub。
2. 打开 EdgeOne Pages 控制台，选择从 Git 仓库导入项目。
3. 选择仓库和分支，根目录保持 `./`。
4. 构建配置可保持默认，EdgeOne Pages 会读取 `edgeone.json`。
5. 部署完成后，EdgeOne Pages 会生成公开访问域名。
6. 后续提交并推送数据或页面更新后，Pages 会自动重新部署。

`edgeone.json` 还配置了：

- HTML 和 JSON 使用 `no-cache`，便于数据更新及时生效。
- CSS、JS、PNG 使用短期缓存。
- JSON 响应带 `Content-Type: application/json; charset=utf-8`。
- `/data/*.json` 允许跨域读取。

## 数据更新

### 客流数据

客流数据由 `scripts/fetch_data.py` 维护，脚本会从南京地铁官方微博组件解析 `#昨日客流#` 内容，更新：

- `data/metro_data.json`
- `data/prediction_log.json`

运行方式：

```bash
python3 scripts/fetch_data.py
```

项目已配置 GitHub Actions 定时任务：`.github/workflows/update-metro-data.yml` 会在北京时间每天 10:15 和 11:15 自动运行，抓取官网微博组件里更新的昨日客流数据，若 `data/metro_data.json` 或 `data/prediction_log.json` 有变化则自动提交并推送到 GitHub。也可以在 GitHub Actions 页面手动触发 `Update metro passenger flow`。

在 CI 中脚本会通过 `METRO_SKIP_GIT=1` 跳过脚本内部的 Git 推送，改由工作流统一提交；本地直接运行脚本时仍保留原来的自动提交并推送到 `origin` 和 `gitee` 的行为。

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
    "last_updated": "2026-04-24",
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
      "date": "2026-04-23",
      "total": 346.31,
      "is_weekend": false,
      "note": "",
      "lines": {
        "L1": 72.61,
        "L2": 60.79
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
│   ├── prediction_log.json    # 预测记录与评估
│   └── raw_data.txt           # 原始数据记录
├── scripts/
│   ├── build-static.sh        # EdgeOne Pages 构建脚本
│   └── fetch_data.py          # 客流数据抓取与预测记录更新
├── update_weather.sh          # 天气数据更新脚本
├── edgeone.json               # EdgeOne Pages 配置
├── vercel.json                # Vercel 静态部署配置
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
- EdgeOne Pages 静态托管

## 许可证

本项目使用 BSD 3-Clause License，完整条款见 `LICENSE`。
