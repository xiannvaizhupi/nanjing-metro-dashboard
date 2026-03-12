#!/bin/bash
# 南京地铁每日数据更新脚本
# 每天早上10点执行

# 设置工作目录
PROJECT_DIR="/Users/zhuzhiwei/项目/nanjing-metro-dashboard"
cd "$PROJECT_DIR"

# 检查虚拟环境或直接执行
if [ -f "venv/bin/python" ]; then
    PYTHON_CMD="venv/bin/python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "未找到Python解释器"
    exit 1
fi

# 执行数据更新脚本
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始执行南京地铁数据更新"
$PYTHON_CMD enhanced_auto_update.py

if [ $? -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 数据更新完成"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 数据更新失败"
fi