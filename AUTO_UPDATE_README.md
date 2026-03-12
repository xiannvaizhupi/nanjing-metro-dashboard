# 南京地铁每日数据自动更新系统

## 📋 功能概述

本系统实现了南京地铁客流数据的每日自动更新，主要功能包括：

### 1. 自动数据获取
- **微博爬取**：每天早上10点自动访问南京地铁官方微博获取客流数据
- **智能解析**：自动解析微博文本中的客流信息
- **备用方案**：微博获取失败时使用最近的数据作为备份

### 2. 数据处理
- **数据验证**：确保数据的完整性和格式正确性
- **自动更新**：将新数据添加到JSON数据文件中
- **版本管理**：保留历史数据，支持数据回溯

### 3. 自动同步
- **Git提交**：自动提交数据变更到本地Git仓库
- **GitHub推送**：自动推送到远程GitHub仓库
- **网站更新**：线上Vercel网站自动更新

## 🕐 执行时间

**每日 10:00 AM** 自动执行更新任务

## 📁 文件结构

```
nanjing-metro-dashboard/
├── enhanced_auto_update.py    # 主要更新脚本
├── weibo_fetcher.py           # 微博数据获取模块
├── run_daily_update.sh        # Shell执行脚本
├── test_data_generator.py     # 测试数据生成器
├── auto_update.py             # 原始更新脚本（已废弃）
├── data/metro_data.json       # 数据文件
└── README.md                  # 项目说明
```

## 🚀 工作流程

```
1. 定时触发
   ↓
2. 微博获取数据
   ↓
3. 数据解析验证
   ↓
4. 更新JSON文件
   ↓
5. Git提交推送
   ↓
6. 网站自动更新
```

## ⚙️ 配置说明

### Cron定时任务
```bash
# 查看定时任务
openclaw cron list

# 任务详情
# - 名称: 南京地铁每日数据更新
# - 时间: 0 10 * * * (每天10点)
# - 命令: sh /Users/zhuzhiwei/项目/nanjing-metro-dashboard/run_daily_update.sh
```

### Git配置
```bash
# 作者配置已在脚本中设置
git config --global user.name "xiaolin"
git config --global user.email "xiaolin@auto.updater"
```

## 🔄 更新日志

### 2026-03-12
- ✅ 实现微博数据获取功能
- ✅ 添加备用数据源机制
- ✅ 设置每日10点自动更新
- ✅ 完成Git自动推送
- ✅ 验证系统运行正常

## 🚨 故障处理

### 微博获取失败
系统会自动使用最近的数据作为备份，确保网站始终有可用数据。

### Git推送失败
- 检查网络连接
- 验证GitHub认证
- 查看Git配置

### 手动触发更新
```bash
cd /Users/zhuzhiwei/项目/nanjing-metro-dashboard
python3 enhanced_auto_update.py
```

## 📊 数据格式

```json
{
  "date": "2026-03-11",
  "total": 315.5,
  "lines": {
    "L1": 68.2,
    "L2": 54.3,
    "L3": 59.8,
    "L4": 17.5,
    "L5": 34.2,
    "L7": 27.6,
    "L10": 18.3,
    "S1": 9.5,
    "S3": 9.7,
    "S6": 5.2,
    "S7": 1.8,
    "S8": 10.1,
    "S9": 2.1
  },
  "is_weekend": false,
  "note": "微博自动获取"
}
```

## 🔧 监控和调试

### 查看执行日志
```bash
# 查看系统日志
tail -f /tmp/openclaw/openclaw-2026-03-12.log | grep "南京地铁"

# 查看Git日志
git log --oneline -10 data/metro_data.json
```

### 测试功能
```bash
# 生成测试数据
python3 test_data_generator.py

# 手动执行更新
python3 enhanced_auto_update.py
```

## 📞 联系支持

如遇问题或需要改进，请通过以下方式联系：
- 查看执行日志
- 运行手动测试
- 检查网络连接