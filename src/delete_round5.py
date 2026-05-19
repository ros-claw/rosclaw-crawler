#!/usr/bin/env python3
"""
第五轮清理 - 最终手动确认29个边界项目
基于实际仓库内容判断
"""

import requests
import json
import re
import time
import os
from datetime import datetime

API_KEY = os.getenv("ROSCALW_API_KEY", "")
BASE_URL = 'https://www.rosclaw.io'
MCP_ENDPOINT = f'{BASE_URL}/api/mcp-packages'
HEADERS = {'Content-Type': 'application/json', 'X-API-Key': API_KEY}

PROGRESS_FILE = 'delete_progress_round5.json'
REVIEW_FILE = 'round4_classification.json'

# 基于实际内容的手动分类
MANUAL_DELETE = [
    # 游戏引擎/3D软件
    'lkysyzxz/MCPForUnity',
    'WENZHELIN/BlenderGNMCP',
    'Gyan-max/MCP-Server-blender',
    'phamhoanggg/MCP_Server_Unity',
    'AccelByte/unreal-sdk-mcp-server',
    # 仿真/物理引擎
    'juijunnarkar/COMSOL_Multiphysics_MCP',
    'devgabrielsborges/bullet-mcp-server',
    'hfujikawa77/ardupilot-mcp-server-sandbox',  # sandbox = 仿真
    # 纯软件工具
    'harness/mcp-server',
    'ejunz-dev/mcp-server',
    'CaseyRo/mcp-lordicon',
    'mimisukeMaster/python-mcp',
    'ccutcliff/MCPi',
    'smslavin/mcp-servers',
    'uniquejava/mcp-server-hello-world',
    'vinupalackal/lightweight_mcp_server',
    'mapbox/mcp-server',
    # 无明确硬件接口
    'PATRAKECU/MCP-Server',
    'Nodeblue-AI/bridge-mcp-server',  # 桥梁，可能是软件抽象
]

MANUAL_KEEP = [
    # 工业/硬件
    'kmanditereza/mcp-server-for-industrial-data',
    'daniguzman32/mcp-server-industrial',
    'gtoff/moveit-mcp-server',  # MoveIt = 机器人运动规划
    # ROS2相关
    'gavindev14/mcp_server_ros_2',
    'kouichiume/llm_mcp_ros2_adapter',
    'darshankt/turtle_mcp_ros2',
    'hirasawagen/mcp_ros2',
    'darshan-kt/turtle_mcp_ros2',
    # 传感器/IoT
    'es617/ble-mcp-server',  # BLE = 蓝牙低功耗，硬件通信
    'ilevin1/mcp-server-deployment-isaacglevin',  # 可能是Isaac Sim部署
]

UNCERTAIN = [
    # 需要进一步确认
    'Nodeblue-AI/bridge-mcp-server',
]

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {'deleted_ids': [], 'failed_ids': [], 'kept_ids': []}

def save_progress(progress):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

def get_all_items():
    resp = requests.get(f'{MCP_ENDPOINT}?page=1&limit=1000', headers=HEADERS, timeout=30)
    data = resp.json()
    return data if isinstance(data, list) else data.get('items', data.get('data', []))

def delete_item(item_id):
    try:
        resp = requests.delete(f'{MCP_ENDPOINT}?id={item_id}', headers=HEADERS, timeout=30)
        return resp.status_code in [200, 201, 204], resp.status_code
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 60)
    print("ROSClaw 第五轮清理 - 手动确认29个边界项目")
    print("=" * 60)
    
    progress = load_progress()
    deleted_ids = set(progress['deleted_ids'])
    
    # 加载第四轮的review项目
    if not os.path.exists(REVIEW_FILE):
        print(f"❌ 找不到 {REVIEW_FILE}，请先运行第四轮清理")
        return
    
    with open(REVIEW_FILE, 'r') as f:
        round4_data = json.load(f)
    
    review_items = round4_data.get('review', [])
    print(f"\n加载 {len(review_items)} 个review项目")
    
    # 获取当前网站上的所有项目（用于获取ID）
    current_items = get_all_items()
    current_map = {}
    for item in current_items:
        url = item.get('githubRepoUrl', '').lower()
        if url:
            # 提取owner/repo
            parts = url.replace('https://github.com/', '').split('/')
            if len(parts) >= 2:
                key = f"{parts[0]}/{parts[1]}".lower()
                current_map[key] = item
    
    # 分类
    to_delete = []
    to_keep = []
    uncertain = []
    
    for review_item in review_items:
        url = review_item.get('url', '').lower()
        name = review_item.get('name', '')
        
        # 提取owner/repo
        parts = url.replace('https://github.com/', '').split('/')
        if len(parts) >= 2:
            key = f"{parts[0]}/{parts[1]}".lower()
        else:
            key = name.lower()
        
        # 找到当前网站上的对应项目
        current_item = current_map.get(key)
        if not current_item:
            print(f"⚠️  找不到项目: {name}")
            continue
        
        if current_item['id'] in deleted_ids:
            continue
        
        # 手动分类
        if key in [k.lower() for k in MANUAL_DELETE]:
            to_delete.append(current_item)
        elif key in [k.lower() for k in MANUAL_KEEP]:
            to_keep.append(current_item)
        elif key in [k.lower() for k in UNCERTAIN]:
            uncertain.append(current_item)
        else:
            # 默认保留
            to_keep.append(current_item)
    
    print(f"\n分类结果:")
    print(f"  ✅ 保留: {len(to_keep)}")
    print(f"  ❌ 删除: {len(to_delete)}")
    print(f"  ⚠️  不确定: {len(uncertain)}")
    
    # 打印待删除项目
    if to_delete:
        print(f"\n=== 待删除项目 ===")
        for item in to_delete:
            print(f"  ❌ {item['name']} | {item.get('githubRepoUrl', '')}")
    
    # 打印保留项目
    if to_keep:
        print(f"\n=== 保留项目 ===")
        for item in to_keep:
            print(f"  ✅ {item['name']} | {item.get('githubRepoUrl', '')}")
    
    # 打印不确定项目
    if uncertain:
        print(f"\n=== 不确定项目 ===")
        for item in uncertain:
            print(f"  ⚠️  {item['name']} | {item.get('githubRepoUrl', '')}")
    
    # 保存分类报告
    report = {
        'timestamp': datetime.now().isoformat(),
        'delete': [{'name': i['name'], 'url': i.get('githubRepoUrl', '')} for i in to_delete],
        'keep': [{'name': i['name'], 'url': i.get('githubRepoUrl', '')} for i in to_keep],
        'uncertain': [{'name': i['name'], 'url': i.get('githubRepoUrl', '')} for i in uncertain],
    }
    with open('round5_classification.json', 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n📄 分类报告已保存: round5_classification.json")
    
    print(f"\n如需执行删除，请运行: python3 delete_round5.py --execute")

def execute_delete():
    progress = load_progress()
    deleted_ids = set(progress['deleted_ids'])
    
    # 加载第五轮分类报告
    if not os.path.exists('round5_classification.json'):
        print(f"❌ 找不到 round5_classification.json，请先运行分类")
        return
    
    with open('round5_classification.json', 'r') as f:
        round5_data = json.load(f)
    
    # 获取当前网站项目
    current_items = get_all_items()
    current_map = {}
    for item in current_items:
        url = item.get('githubRepoUrl', '').lower()
        if url:
            parts = url.replace('https://github.com/', '').split('/')
            if len(parts) >= 2:
                key = f"{parts[0]}/{parts[1]}".lower()
                current_map[key] = item
    
    to_delete = []
    for item_data in round5_data.get('delete', []):
        url = item_data.get('url', '').lower()
        parts = url.replace('https://github.com/', '').split('/')
        if len(parts) >= 2:
            key = f"{parts[0]}/{parts[1]}".lower()
            current_item = current_map.get(key)
            if current_item and current_item['id'] not in deleted_ids:
                to_delete.append(current_item)
    
    print(f"\n执行删除: {len(to_delete)} 个项目")
    
    success = 0
    failed = 0
    
    for i, item in enumerate(to_delete, 1):
        item_id = item['id']
        name = item['name']
        
        print(f"\n[{i}/{len(to_delete)}] {name}")
        
        ok, code = delete_item(item_id)
        if ok:
            success += 1
            progress['deleted_ids'].append(item_id)
            print(f"  ✅ 删除成功 ({code})")
        else:
            failed += 1
            progress['failed_ids'].append(item_id)
            print(f"  ❌ 删除失败 ({code})")
        
        save_progress(progress)
        
        if i % 5 == 0:
            time.sleep(2)
        else:
            time.sleep(0.5)
    
    print(f"\n{'='*60}")
    print("第五轮清理完成!")
    print(f"成功: {success}, 失败: {failed}")
    
    remaining = get_all_items()
    print(f"剩余MCP: {len(remaining)}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--execute':
        execute_delete()
    else:
        main()
