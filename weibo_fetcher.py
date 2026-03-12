#!/usr/bin/env python3
"""
微博数据获取模块
提供多种方式获取南京地铁客流数据
"""

import requests
import re
from datetime import datetime

class WeiboDataFetcher:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
    
    def fetch_from_weibo_search(self):
        """从微博搜索获取数据"""
        try:
            # 使用微博移动端搜索
            search_url = "https://m.weibo.cn/search/container/page"
            params = {
                'containerid': '100103%3Atype_5106985820729011',  # 南京地铁官方
                'page_type': 'searchall',
                'keyword': '南京地铁 客流'
            }
            
            response = requests.get(search_url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code == 200:
                # 使用正则表达式直接从HTML中提取
                html_content = response.text
                
                # 查找包含客流数据的模式
                pattern = r'(\d{1,2}-\d{1,2}-\d{1,2})#昨日客流#南京地铁(\d{1,2})月(\d{1,2})日客运量(\d+(?:\.\d+)?)[^，]*，(.+?)（以上单位: 万）'
                matches = re.findall(pattern, html_content)
                
                if matches:
                    return matches[0]  # 返回第一个匹配结果
                    
            return None
            
        except Exception as e:
            print(f"微博搜索获取失败: {e}")
            return None
    
    def fetch_from_account_page(self):
        """从账号主页获取数据"""
        try:
            url = "https://m.weibo.cn/u/2109896777"  # 南京地铁官方微博ID
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                html_content = response.text
                
                # 查找最新的客流微博
                pattern = r'(\d{1,2}-\d{1,2}-\d{1,2})#昨日客流#南京地铁(\d{1,2})月(\d{1,2})日客运量(\d+(?:\.\d+)?)[^，]*，(.+?)（以上单位: 万）'
                matches = re.findall(pattern, html_content)
                
                if matches:
                    return matches[0]
                    
            return None
            
        except Exception as e:
            print(f"账号主页获取失败: {e}")
            return None
    
    def fetch_data(self):
        """获取客流数据"""
        print("正在尝试从微博获取数据...")
        
        # 尝试多种方法
        methods = [
            ("微博搜索", self.fetch_from_weibo_search),
            ("账号主页", self.fetch_from_account_page),
        ]
        
        for method_name, method in methods:
            print(f"尝试使用 {method_name}...")
            result = method()
            if result:
                print(f"✅ {method_name} 成功获取数据!")
                return result
            print(f"❌ {method_name} 失败")
        
        print("所有方法都失败了，需要手动干预")
        return None

def parse_metro_data(match_result):
    """解析匹配到的数据"""
    if not match_result:
        return None
    
    _, month, day, total, lines_data = match_result
    
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
        "is_weekend": False,
        "note": "微博自动获取"
    }

if __name__ == "__main__":
    fetcher = WeiboDataFetcher()
    result = fetcher.fetch_data()
    
    if result:
        data = parse_metro_data(result)
        print(f"获取成功: {data}")
    else:
        print("获取失败")