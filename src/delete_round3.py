#!/usr/bin/env python3
"""
第三轮清理 - 对review项目进行LLM验证
确认是否真正实现MCP协议 + 有物理硬件接口
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

PROGRESS_FILE = 'delete_progress_round3.json'

# 从第二轮分类报告中加载review项目
REVIEW_FILE = 'round2_classification.json'

# 明确删除规则（基于名称判断）
DELETE_PATTERNS = [
    # 游戏引擎
    r'unreal[\s\-_]?mcp', r'unity[\s\-_]?mcp', r'ue[\s\-_]?mcp',
    r'MCPForUnity', r'MCP_Server_Unity', r'unity[\s\-_]?copilot',
    r'mcp[\s\-_]?unreal', r'unreal[\s\-_]?analyzer',
    r'blender[\s\-_]?mcp', r'blender[\s\-_]?server',
    r'cadquery[\s\-_]?mcp', r'cadcamfun',
    r'fusion[\s\-_]?360[\s\-_]?mcp', r'eyeshot[\s\-_]?cad',
    r'rhino[\s\-_]?mcp', r'golem[\s\-_]?3dmcp',
    # 仿真/CAE
    r'isaac[\s\-_]?sim', r'isaac[\s\-_]?lab', r'gazebo[\s\-_]?mcp',
    r'pybullet[\s\-_]?mcp', r'mujoco[\s\-_]?mcp',
    r'comsol[\s\-_]?mcp', r'energyplus',
    r'mlagents[\s\-_]?mcp',
    # 纯软件工具
    r'web[\s\-_]?fetch', r'go[\s\-_]?web[\s\-_]?fetch',
    r'lordicon[\s\-_]?mcp', r'shadcn[\s\-_]?ui',
    r'proptech[\s\-_]?mcp', r'roster[\s\-_]?generator',
    r'undesirables[\s\-_]?mcp', r'barf[\s\-_]?mcp',
    r'ssh[\s\-_]?mcp', r'cnc[\s\-_]?youtube',
    r'dart[\s\-_]?mcp', r'metoro[\s\-_]?mcp',
    r'mapbox[\s\-_]?mcp', r'crabcut',
    r'vectorize[\s\-_]?mcp',
    # 非硬件传感器
    r'ambient[\s\-_]?sensor', r'sensorbio',
    r'framegrab',
    # 软件框架
    r'kapua[\s\-_]?mcp', r'thingspanel',
    r'omni[\s\-_]?fun', r'harness[\s\-_]?mcp',
    r'ejunz[\s\-_]?mcp', r'integration[\s\-_]?app',
    r'membrane[\s\-_]?mcp',
    # 无硬件接口
    r'picotool', r'MCPi', r'pybullet',
    r'particle[\s\-_]?physics',
    r'energyatit',
    r'akramiot', r'zta[\s\-_]?mcp',
    r'fyta[\s\-_]?mcp',
    # 成人/非硬件
    r'buttplug',
    # 纯软件ROS工具
    r'ros2[\s\-_]?logs', r'ros[\s\-_]?bridge[\s\-_]?mcp',
    r'nav2[\s\-_]?mcp[\s\-_]?server',  # 纯导航，无硬件
    r'perception[\s\-_]?mcp',  # 纯感知，无硬件
    r'cv[\s\-_]?mcp',  # 纯计算机视觉
    r'langgraph[\s\-_]?mcp',  # 纯AI框架
    # 其他
    r'hardware[\s\-_]?store',  # 商店，不是硬件控制
    r'ardupilot[\s\-_]?sandbox',  # 仿真
    r'safie[\s\-_]?api',  # API接口，不是直接硬件控制
    r'openbci',  # 脑机接口，虽然是硬件但属于生物医疗
    r'lidarr',  # 音频工具
    r' studio[\s\-_]?5000',  # 软件IDE
    r'tia[\s\-_]?portal',  # 软件IDE
    r'br[\s\-_]?automation[\s\-_]?pvi',  # 软件接口
    r'opc[\s\-_]?ua',  # 纯OPC UA，无硬件
    r'mdbus',  # 拼写错误，且可能是纯软件
]

# 明确保留规则（物理硬件）
KEEP_PATTERNS = [
    r'arduino', r'esp32', r'raspberry[\s\-_]?pi',
    r'klipper', r'bambu', r'prusa', r'3d[\s\-_]?printer',
    r'cnc', r'plc', r'modbus', r'opcua', r'beckhoff',
    r'stamplc', r's7[\s\-_]?mcp', r'tiaopen',
    r'ros[\s\-_]?claw', r'ros[\s\-_]?mcp', r'ros2[\s\-_]?mcp',
    r'robot', r'drone', r'uav', r'tello',
    r'servo', r'motor', r'led', r'camera',
    r'lidar', r'sensor', r'iot', r'zigbee',
    r'serial', r'mqtt', r'mavlink',
    r'unitree', r'go2', r'turtlebot',
    r'ur[\s\-_]?rtde', r'universal[\s\-_]?robots',
    r'inspire[\s\-_]?rh56',
    r'gimbal', r'librealsense',
    r'navado[\s\-_]?esp32',
    r'mikehatch[\s\-_]?klipper',
    r'cadugrillo[\s\-_]?s7',
    r'visualboy[\s\-_]?mcp',
    r'ion[\s\-_]?mavlink',
    r'dmontgomery40[\s\-_]?bambu',
    r'dmontgomery40[\s\-_]?mcp',
    r'kukapay[\s\-_]?opcua',
    r'midhunxavier[\s\-_]?opcua',
    r'ekakit[\s\-_]?lightfast',
    r'macromnex[\s\-_]?gromacs',
    r'mushroomfleet[\s\-_]?robot',
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

def classify_review_item(item):
    """对review项目进行自动分类"""
    name = item.get('name', '').lower()
    url = item.get('githubRepoUrl', '').lower()
    text = f'{name} {url}'
    
    # 1. 检查保留规则
    for pattern in KEEP_PATTERNS:
        if re.search(pattern, text):
            return 'keep', f'Keep pattern: {pattern}'
    
    # 2. 检查删除规则
    for pattern in DELETE_PATTERNS:
        if re.search(pattern, text):
            return 'delete', f'Delete pattern: {pattern}'
    
    # 3. 默认保留（需要进一步确认）
    return 'review', 'Still needs review'

def delete_item(item_id):
    try:
        resp = requests.delete(f'{MCP_ENDPOINT}?id={item_id}', headers=HEADERS, timeout=30)
        return resp.status_code in [200, 201, 204], resp.status_code
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 60)
    print("ROSClaw 第三轮清理 - Review项目自动分类")
    print("=" * 60)
    
    progress = load_progress()
    deleted_ids = set(progress['deleted_ids'])
    
    # 加载第二轮的review项目
    if not os.path.exists(REVIEW_FILE):
        print(f"❌ 找不到 {REVIEW_FILE}，请先运行第二轮清理")
        return
    
    with open(REVIEW_FILE, 'r') as f:
        round2_data = json.load(f)
    
    review_items = round2_data.get('review', [])
    print(f"\n加载 {len(review_items)} 个review项目")
    
    # 获取当前网站上的所有项目（用于获取ID）
    current_items = get_all_items()
    current_map = {item.get('githubRepoUrl', '').lower(): item for item in current_items}
    
    # 分类
    to_delete = []
    to_keep = []
    still_review = []
    
    for review_item in review_items:
        url = review_item.get('url', '').lower()
        name = review_item.get('name', '').lower()
        
        # 找到当前网站上的对应项目
        current_item = current_map.get(url)
        if not current_item:
            print(f"⚠️  找不到项目: {name}")
            continue
        
        if current_item['id'] in deleted_ids:
            continue
        
        result, reason = classify_review_item(current_item)
        current_item['_result'] = result
        current_item['_reason'] = reason
        
        if result == 'delete':
            to_delete.append(current_item)
        elif result == 'keep':
            to_keep.append(current_item)
        else:
            still_review.append(current_item)
    
    print(f"\n分类结果:")
    print(f"  ✅ 保留: {len(to_keep)}")
    print(f"  ❌ 删除: {len(to_delete)}")
    print(f"  ⚠️  仍需确认: {len(still_review)}")
    
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
    
    # 打印仍需确认的项目
    if still_review:
        print(f"\n=== 仍需确认的项目 ===")
        for item in still_review:
            print(f"  ⚠️  {item['name']} | {item.get('githubRepoUrl', '')}")
    
    # 保存分类报告
    report = {
        'timestamp': datetime.now().isoformat(),
        'delete': [{'name': i['name'], 'url': i.get('githubRepoUrl', ''), 'reason': i['_reason']} for i in to_delete],
        'keep': [{'name': i['name'], 'url': i.get('githubRepoUrl', ''), 'reason': i['_reason']} for i in to_keep],
        'review': [{'name': i['name'], 'url': i.get('githubRepoUrl', ''), 'reason': i['_reason']} for i in still_review],
    }
    with open('round3_classification.json', 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n📄 分类报告已保存: round3_classification.json")
    
    print(f"\n如需执行删除，请运行: python3 delete_round3.py --execute")

def execute_delete():
    progress = load_progress()
    deleted_ids = set(progress['deleted_ids'])
    
    # 加载第三轮分类报告
    if not os.path.exists('round3_classification.json'):
        print(f"❌ 找不到 round3_classification.json，请先运行分类")
        return
    
    with open('round3_classification.json', 'r') as f:
        round3_data = json.load(f)
    
    # 获取当前网站项目
    current_items = get_all_items()
    current_map = {item.get('githubRepoUrl', '').lower(): item for item in current_items}
    
    to_delete = []
    for item_data in round3_data.get('delete', []):
        url = item_data.get('url', '').lower()
        current_item = current_map.get(url)
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
    print("第三轮清理完成!")
    print(f"成功: {success}, 失败: {failed}")
    
    remaining = get_all_items()
    print(f"剩余MCP: {len(remaining)}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--execute':
        execute_delete()
    else:
        main()
