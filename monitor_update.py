#!/usr/bin/env python3
"""
南京地铁数据更新监控系统
检查自动更新系统的运行状态
"""

import json
import os
from datetime import datetime, timedelta
import subprocess
import sys

def check_last_update():
    """检查最后更新时间"""
    data_file = "/Users/zhuzhiwei/项目/nanjing-metro-dashboard/data/metro_data.json"
    
    if not os.path.exists(data_file):
        return {"status": "error", "message": "数据文件不存在"}
    
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if data.get('data') and len(data['data']) > 0:
            latest_data = data['data'][0]
            latest_date = latest_data['date']
            
            # 计算日期差
            latest = datetime.strptime(latest_date, '%Y-%m-%d')
            today = datetime.now()
            days_diff = (today - latest).days
            
            return {
                "status": "success",
                "latest_date": latest_date,
                "days_diff": days_diff,
                "total_passengers": latest_data['total'],
                "note": latest_data['note']
            }
        else:
            return {"status": "error", "message": "数据文件为空"}
            
    except Exception as e:
        return {"status": "error", "message": f"读取数据文件失败: {e}"}

def check_cron_job():
    """检查定时任务状态"""
    try:
        result = subprocess.run(['openclaw', 'cron', 'list'], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            # 查找南京地铁相关的任务
            lines = result.stdout.split('\n')
            for line in lines:
                if '南京地铁' in line:
                    return {
                        "status": "found",
                        "details": line.strip()
                    }
            return {"status": "not_found", "message": "未找到南京地铁任务"}
        else:
            return {"status": "error", "message": f"获取任务列表失败: {result.stderr}"}
            
    except Exception as e:
        return {"status": "error", "message": f"检查定时任务失败: {e}"}

def check_git_status():
    """检查Git状态"""
    project_dir = "/Users/zhuzhiwei/项目/nanjing-metro-dashboard"
    
    try:
        # 检查工作目录
        os.chdir(project_dir)
        
        # 检查未提交的更改
        result = subprocess.run(['git', 'status', '--porcelain'], 
                              capture_output=True, text=True, timeout=5)
        
        uncommitted = bool(result.stdout.strip())
        
        # 检查远程连接
        result = subprocess.run(['git', 'remote', 'get-url', 'origin'], 
                              capture_output=True, text=True, timeout=5)
        
        has_remote = result.returncode == 0
        
        return {
            "status": "success",
            "uncommitted_changes": uncommitted,
            "remote_connected": has_remote,
            "project_directory": project_dir
        }
        
    except Exception as e:
        return {"status": "error", "message": f"检查Git状态失败: {e}"}

def generate_report():
    """生成监控报告"""
    print("🚇 南京地铁数据更新系统监控报告")
    print("=" * 50)
    print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 检查数据更新
    print("📊 数据更新状态:")
    update_check = check_last_update()
    
    if update_check["status"] == "success":
        days_diff = update_check["days_diff"]
        if days_diff == 0:
            print(f"  ✅ 数据最新 ({update_check['latest_date']})")
        elif days_diff == 1:
            print(f"  ⚠️  数据落后1天 ({update_check['latest_date']})")
        else:
            print(f"  ❌ 数据落后{days_diff}天 ({update_check['latest_date']})")
        
        print(f"  📈 最新客流: {update_check['total_passengers']}万人")
        print(f"  📝 备注: {update_check['note']}")
    else:
        print(f"  ❌ {update_check['message']}")
    
    print()
    
    # 检查定时任务
    print("⏰ 定时任务状态:")
    cron_check = check_cron_job()
    
    if cron_check["status"] == "found":
        print("  ✅ 定时任务已配置")
        print(f"  📋 {cron_check['details']}")
    else:
        print(f"  ❌ {cron_check['message']}")
    
    print()
    
    # 检查Git状态
    print("🔧 Git状态:")
    git_check = check_git_status()
    
    if git_check["status"] == "success":
        print(f"  📁 项目目录: {git_check['project_directory']}")
        print(f"  🔄 远程连接: {'✅ 正常' if git_check['remote_connected'] else '❌ 失败'}")
        print(f"  📝 未提交更改: {'✅ 无' if not git_check['uncommitted_changes'] else '⚠️ 有'}")
        
        if git_check['uncommitted_changes']:
            print("  💡 建议运行: git add . && git commit -m 'update'")
    else:
        print(f"  ❌ {git_check['message']}")
    
    print()
    
    # 生成建议
    print("💡 系统建议:")
    
    if update_check["status"] == "success" and update_check["days_diff"] > 1:
        print("  📅 微博数据获取可能存在问题，建议手动检查")
    
    if git_check["status"] == "success" and git_check['uncommitted_changes']:
        print("  🔄 有未提交的更改，建议及时提交并推送")
    
    print("  🧪 可以运行 python3 enhanced_auto_update.py 手动触发更新")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    generate_report()