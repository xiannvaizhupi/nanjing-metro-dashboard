#!/usr/bin/env python3
"""
南京地铁客流数据自动抓取脚本
每日10:00执行，从南京地铁官网微博组件获取昨日客流数据
"""

import json
import re
from datetime import datetime, date
from urllib.request import urlopen
from urllib.parse import quote

def fetch_weibo_data():
    """从南京地铁官网微博组件获取数据"""
    url = "https://widget.weibo.com/weiboshow/index.php?language=&width=0&height=430&fansRow=1&ptype=1&speed=0&skin=1&isTitle=1&noborder=1&isWeibo=1&isFans=0&uid=2638276292&verifier=138e3b0a&dpc=1"
    
    try:
        response = urlopen(url, timeout=30)
        html = response.read().decode('utf-8')
        return html
    except Exception as e:
        print(f"获取微博数据失败: {e}")
        return None

def parse_weibo_flow(html):
    """解析微博内容中的客流数据"""
    if not html:
        return []
    
    results = []
    # 匹配 #昨日客流# 格式的数据
    pattern = r'#昨日客流#[^#]*南京地铁(\d+)月(\d+)日客运量(\d+\.?\d*)[，,]([^#\n]+)（以上单位'
    
    for match in re.finditer(pattern, html):
        month = int(match.group(1))
        day = int(match.group(2))
        total = float(match.group(3))
        lines_str = match.group(4)
        
        year = 2026  # 或使用当前年份
        date_str = f"{year}-{month:02d}-{day:02d}"
        
        # 解析各线路
        lines = {}
        line_patterns = [
            (r'1号线(\d+\.?\d*)', 'L1'),
            (r'2号线(\d+\.?\d*)', 'L2'),
            (r'3号线(\d+\.?\d*)', 'L3'),
            (r'4号线(\d+\.?\d*)', 'L4'),
            (r'5号线(\d+\.?\d*)', 'L5'),
            (r'7号线(\d+\.?\d*)', 'L7'),
            (r'10号线(\d+\.?\d*)', 'L10'),
            (r'S1号线(\d+\.?\d*)', 'S1'),
            (r'S3号线(\d+\.?\d*)', 'S3'),
            (r'S6号线(\d+\.?\d*)', 'S6'),
            (r'S7号线(\d+\.?\d*)', 'S7'),
            (r'S8号线(\d+\.?\d*)', 'S8'),
            (r'S9号线(\d+\.?\d*)', 'S9'),
        ]
        
        for pattern, line_id in line_patterns:
            m = re.search(pattern, lines_str)
            if m:
                lines[line_id] = float(m.group(1))
        
        d = date(year, month, day)
        is_weekend = d.weekday() >= 5
        
        results.append({
            'date': date_str,
            'total': total,
            'is_weekend': is_weekend,
            'note': '',
            'lines': lines
        })
        
        print(f"解析: {date_str} - {total}万")
    
    return results

def update_metro_data(new_entries):
    """更新metro_data.json"""
    try:
        with open('data/metro_data.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("metro_data.json 不存在")
        return False
    
    existing_dates = {item['date'] for item in data['daily_data']}
    updated = False
    
    for entry in new_entries:
        entry_date = entry['date']
        if entry_date in existing_dates:
            # 更新已有数据
            for i, item in enumerate(data['daily_data']):
                if item['date'] == entry_date:
                    data['daily_data'][i] = entry
                    print(f"更新: {entry_date}")
                    updated = True
                    break
        else:
            # 添加新数据
            data['daily_data'].append(entry)
            print(f"添加: {entry_date}")
            updated = True
    
    if updated:
        # 按日期排序
        data['daily_data'].sort(key=lambda x: x['date'])
        
        # 更新 metadata
        data['metadata']['last_updated'] = datetime.now().strftime('%Y-%m-%d')
        data['metadata']['fetched_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 保存
        with open('data/metro_data.json', 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"数据已保存到 metro_data.json")
        return True
    else:
        print("没有新数据需要更新")
        return False

def main():
    import subprocess
    
    print(f"=== 南京地铁客流数据抓取 ===")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 获取数据
    html = fetch_weibo_data()
    
    # 解析
    entries = parse_weibo_flow(html)
    
    if entries:
        # 更新
        if update_metro_data(entries):
            print("\n数据更新成功，准备推送...")
            
            # Git 推送
            try:
                repo_dir = '/Users/zhuzhiwei/nanjing-metro-dashboard'
                commit_msg = f"Auto update metro data - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                
                subprocess.run(['git', 'add', '.'], cwd=repo_dir, check=True)
                subprocess.run(['git', 'commit', '-m', commit_msg], cwd=repo_dir, check=True)
                result = subprocess.run(['git', 'push'], cwd=repo_dir, capture_output=True, text=True)
                
                if result.returncode == 0:
                    print("Git 推送成功!")
                else:
                    print(f"Git 推送失败: {result.stderr}")
            except Exception as e:
                print(f"Git 操作失败: {e}")
        else:
            print("\n数据更新失败或无新数据")
    else:
        print("\n未解析到客流数据")

if __name__ == '__main__':
    main()
