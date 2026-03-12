#!/usr/bin/env python3
"""
南京地铁每日数据自动更新脚本
功能：每天10点自动从微博获取客流数据并更新到GitHub
"""

import requests
import json
import re
import os
from datetime import datetime, timedelta
import subprocess
import time
from weibo_fetcher import WeiboDataFetcher

def get_weibo_data():
    """获取南京地铁微博最新数据"""
    try:
        fetcher = WeiboDataFetcher()
        match_result = fetcher.fetch_data()
        
        if match_result:
            # 解析匹配结果
            _, month, day, total, lines_data = match_result
            return f"{month.zfill(2)}-{day.zfill(2)}#昨日客流#南京地铁{month}月{day}日客运量{total}，{lines_data}（以上单位: 万）"
        
        return None
        
    except Exception as e:
        print(f"获取微博数据失败: {e}")
        return None

def parse_metro_data(text):
    """解析微博文本中的客流数据"""
    if not text:
        return None
    
    # 匹配客流数据模式
    pattern = r'(\d{1,2}-\d{1,2}-\d{1,2})#昨日客流#南京地铁(\d{1,2})月(\d{1,2})日客运量(\d+(?:\.\d+)?)[^，]*，(.+?)（以上单位: 万）'
    match = re.search(pattern, text)
    
    if not match:
        return None
    
    # 提取数据
    _, month, day, total, lines_data = match.groups()
    
    # 构建日期
    current_year = datetime.now().year
    date_str = f"{current_year}-{month.zfill(2)}-{day.zfill(2)}"
    
    # 解析各线路数据
    lines_dict = {}
    line_pattern = r'(\d+)号线[：:](\d+(?:\.\d+)?)'
    line_matches = re.findall(line_pattern, lines_data)
    
    for line_num, passenger_count in line_matches:
        line_key = f"L{line_num}"
        lines_dict[line_key] = float(passenger_count)
    
    # 处理S线
    s_line_pattern = r'S(\d+)号线[：:](\d+(?:\.\d+)?)'
    s_line_matches = re.findall(s_line_pattern, lines_data)
    
    for line_num, passenger_count in s_line_matches:
        line_key = f"S{line_num}"
        lines_dict[line_key] = float(passenger_count)
    
    return {
        "date": date_str,
        "total": float(total),
        "lines": lines_dict,
        "is_weekend": False,  # 可以根据实际日期计算
        "note": "自动获取"
    }

def update_data_file(new_data):
    """更新数据文件"""
    data_file = "/Users/zhuzhiwei/项目/nanjing-metro-dashboard/data/metro_data.json"
    
    # 读取现有数据
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
    else:
        existing_data = {"data": []}
    
    # 添加新数据
    if "data" not in existing_data:
        existing_data["data"] = []
    
    # 检查是否已有当天的数据
    for i, item in enumerate(existing_data["data"]):
        if item["date"] == new_data["date"]:
            existing_data["data"][i] = new_data
            break
    else:
        existing_data["data"].insert(0, new_data)
    
    # 更新元数据
    existing_data["metadata"]["last_updated"] = new_data["date"]
    
    # 保存文件
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
    
    return data_file

def commit_and_push():
    """提交并推送到GitHub"""
    project_dir = "/Users/zhuzhiwei/项目/nanjing-metro-dashboard"
    
    try:
        # 切换到项目目录
        os.chdir(project_dir)
        
        # Git操作
        subprocess.run(['git', 'add', 'data/metro_data.json'], check=True)
        subprocess.run(['git', 'commit', '-m', f'Update data: {datetime.now().strftime("%Y-%m-%d %H:%M")}', '--author=xiao.lin@auto.updater'], check=True)
        subprocess.run(['git', 'push'], check=True)
        
        print("GitHub推送成功!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Git操作失败: {e}")
        return False

def main():
    print("开始执行每日数据更新...")
    
    # 1. 获取微博数据
    print("正在获取微博数据...")
    weibo_text = get_weibo_data()
    if not weibo_text:
        print("未获取到微博数据，中止执行")
        return
    
    # 2. 解析数据
    print("正在解析客流数据...")
    parsed_data = parse_metro_data(weibo_text)
    if not parsed_data:
        print("解析数据失败，中止执行")
        return
    
    print(f"成功解析数据: {parsed_data['date']} 总客流: {parsed_data['total']}万人")
    
    # 3. 更新数据文件
    print("正在更新数据文件...")
    data_file = update_data_file(parsed_data)
    print(f"数据已更新到: {data_file}")
    
    # 4. 推送到GitHub
    print("正在推送到GitHub...")
    if commit_and_push():
        print("每日数据更新完成! ✅")
    else:
        print("GitHub推送失败 ❌")

if __name__ == "__main__":
    main()