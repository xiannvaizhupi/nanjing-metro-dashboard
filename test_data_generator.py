#!/usr/bin/env python3
"""
测试数据生成脚本 - 用于验证自动更新功能
"""

import json
from datetime import datetime, timedelta

def generate_test_data():
    """生成测试客流数据"""
    # 生成昨天日期
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime("%Y-%m-%d")
    
    # 生成示例客流数据
    test_data = {
        "date": date_str,
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
        "is_weekend": yesterday.weekday() >= 5,
        "note": "测试数据"
    }
    
    return test_data

def save_test_data():
    """保存测试数据到文件"""
    data_file = "/Users/zhuzhiwei/项目/nanjing-metro-dashboard/data/metro_data.json"
    
    # 读取现有数据
    import os
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
    else:
        existing_data = {"data": []}
    
    # 添加测试数据
    new_data = generate_test_data()
    
    if "data" not in existing_data:
        existing_data["data"] = []
    
    # 添加或更新数据
    found = False
    for i, item in enumerate(existing_data["data"]):
        if item["date"] == new_data["date"]:
            existing_data["data"][i] = new_data
            found = True
            break
    
    if not found:
        existing_data["data"].insert(0, new_data)
    
    # 更新元数据
    existing_data["metadata"]["last_updated"] = new_data["date"]
    
    # 保存文件
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
    
    print(f"测试数据已保存到: {data_file}")
    print(f"数据日期: {new_data['date']}")
    print(f"总客流: {new_data['total']}万人")
    
    return data_file

if __name__ == "__main__":
    save_test_data()