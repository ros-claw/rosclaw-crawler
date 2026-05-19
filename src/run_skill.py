#!/usr/bin/env python3
"""
ROSClaw 定向抓取 + 严格分析 Skill
一键执行完整流程
"""
import subprocess
import sys

def run_step(name, script):
    """执行步骤"""
    print(f"\n{'='*80}")
    print(f"步骤: {name}")
    print(f"{'='*80}")
    result = subprocess.run([sys.executable, script], capture_output=False)
    return result.returncode == 0

def main():
    print("=" * 80)
    print("ROSClaw Skill - 定向抓取 + 严格分析")
    print("=" * 80)
    
    # 步骤1: 定向抓取
    if not run_step("定向抓取具身智能Agent项目", "rosclaw_crawler/targeted_crawl.py"):
        print("❌ 抓取失败")
        return
    
    # 步骤2: 严格分析
    if not run_step("DeepSeek V4 Pro严格审核", "rosclaw_crawler/strict_analyze.py"):
        print("❌ 分析失败")
        return
    
    # 步骤3: 生成清单
    if not run_step("生成可上传清单", "rosclaw_crawler/generate_upload_list.py"):
        print("❌ 清单生成失败")
        return
    
    print("\n" + "=" * 80)
    print("✅ 全部完成！请检查 upload_list_*.json 文件确认上传项目")
    print("=" * 80)

if __name__ == '__main__':
    main()
