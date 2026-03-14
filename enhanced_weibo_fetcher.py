#!/usr/bin/env python3
"""
微博数据获取增强版
尝试多种方法获取南京地铁客流数据
"""

import requests
import json
import re
import os
from datetime import datetime, timedelta
from urllib.parse import quote

class EnhancedWeiboFetcher:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
    def fetch_with_direct_weibo(self):
        """直接访问微博搜索页面"""
        try:
            print("尝试方法1: 直接微博搜索...")
            # 南京地铁微博主页
            url = "https://weibo.com/u/2109896777"
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                html_content = response.text
                
                # 查找客流数据
                pattern = r'(\d{1,2}-\d{1,2}-\d{1,2})#昨日客流#南京地铁(\d{1,2})月(\d{1,2})日客运量(\d+(?:\.\d+)?)[^，]*，(.+?)（以上单位: 万）'
                matches = re.findall(pattern, html_content)
                
                if matches:
                    result = matches[0]
                    print("✅ 直接微博搜索成功!")
                    return result
                else:
                    print("❌ 未找到客流数据模式")
                    
        except Exception as e:
            print(f"❌ 直接微博搜索失败: {e}")
            
        return None
    
    def fetch_with_sogou_search(self):
        """使用搜狗微博搜索"""
        try:
            print("尝试方法2: 搜狗微博搜索...")
            
            # 搜狗微博搜索
            search_url = "https://weibo.sogou.com/weibo"
            params = {
                'query': '南京地铁 客流',
                'page': 1,
                'type': 1
            }
            
            response = requests.get(search_url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code == 200:
                html_content = response.text
                
                pattern = r'(\d{1,2}-\d{1,2}-\d{1,2})#昨日客流#南京地铁(\d{1,2})月(\d{1,2})日客运量(\d+(?:\.\d+)?)[^，]*，(.+?)（以上单位: 万）'
                matches = re.findall(pattern, html_content)
                
                if matches:
                    result = matches[0]
                    print("✅ 搜狗微博搜索成功!")
                    return result
                else:
                    print("❌ 搜狗搜索未找到数据")
                    
        except Exception as e:
            print(f"❌ 搜狗微博搜索失败: {e}")
            
        return None
    
    def fetch_with_baidu_search(self):
        """使用百度搜索"""
        try:
            print("尝试方法3: 百度搜索...")
            
            # 百度搜索
            search_url = "https://www.baidu.com/s"
            params = {
                'wd': '南京地铁 客流 site:weibo.com',
                'rn': '20'
            }
            
            response = requests.get(search_url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code == 200:
                html_content = response.text
                
                # 提取微博链接并访问
                weibo_links = re.findall(r'href="https://weibo\.com/[^\s"]*"', html_content)
                
                for link in weibo_links[:3]:  # 只尝试前3个链接
                    link_url = re.search(r'"([^"]*)"', link).group(1)
                    
                    try:
                        weibo_response = requests.get(link_url, headers=self.headers, timeout=20)
                        if weibo_response.status_code == 200:
                            weibo_content = weibo_response.text
                            
                            pattern = r'(\d{1,2}-\d{1,2}-\d{1,2})#昨日客流#南京地铁(\d{1,2})月(\d{1,2})日客运量(\d+(?:\.\d+)?)[^，]*，(.+?)（以上单位: 万）'
                            matches = re.findall(pattern, weibo_content)
                            
                            if matches:
                                result = matches[0]
                                print("✅ 百度搜索+微博访问成功!")
                                return result
                    except:
                        continue
                        
        except Exception as e:
            print(f"❌ 百度搜索失败: {e}")
            
        return None
    
    def fetch_recent_news(self):
        """尝试获取新闻网站数据"""
        try:
            print("尝试方法4: 新闻网站搜索...")
            
            # 尝试南京发布等官方账号
            news_urls = [
                "https://weibo.com/nanjingfabu",
                "https://weibo.com/nanjingmetro"
            ]
            
            for url in news_urls:
                try:
                    response = requests.get(url, headers=self.headers, timeout=20)
                    if response.status_code == 200:
                        html_content = response.text
                        
                        pattern = r'(\d{1,2}-\d{1,2}-\d{1,2})#昨日客流#南京地铁(\d{1,2})月(\d{1,2})日客运量(\d+(?:\.\d+)?)[^，]*，(.+?)（以上单位: 万）'
                        matches = re.findall(pattern, html_content)
                        
                        if matches:
                            result = matches[0]
                            print(f"✅ {url} 成功!")
                            return result
                except:
                    continue
                    
        except Exception as e:
            print(f"❌ 新闻网站搜索失败: {e}")
            
        return None
    
def fetch_correct_data():
    """获取正确的客流数据"""
    fetcher = EnhancedWeiboFetcher()
    
    methods = [
        ("直接微博搜索", fetcher.fetch_with_direct_weibo),
        ("搜狗微博搜索", fetcher.fetch_with_sogou_search),
        ("百度搜索", fetcher.fetch_with_baidu_search),
        ("新闻网站搜索", fetcher.fetch_recent_news),
    ]
    
    for method_name, method in methods:
        print(f"\n=== {method_name} ===")
        result = method()
        if result:
            return result
    
    # 所有方法都失败，返回 None（不允许模拟数据）
    print("\n❌ 所有数据获取方法都失败，未获取到真实数据")
    return None

if __name__ == "__main__":
    result = fetch_correct_data()
    
    if result:
        date_pattern, month, day, total, lines_text = result
        print(f"\n🎉 成功获取数据:")
        print(f"日期: {month}月{day}日")
        print(f"总客流: {total}万人")
        print(f"线路数据: {lines_text}")
    else:
        print("❌ 所有方法都失败了")