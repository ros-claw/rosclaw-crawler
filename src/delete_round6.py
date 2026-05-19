#!/usr/bin/env python3
"""
第六轮清理 - 对剩余184个进行最终LLM验证
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

PROGRESS_FILE = 'delete_progress_round6.json'

# 明确删除规则（最终版）
DELETE_PATTERNS = [
    # 游戏引擎/3D软件
    r'unreal[\s\-_]?mcp', r'unity[\s\-_]?mcp', r'ue[\s\-_]?mcp',
    r'blender[\s\-_]?mcp', r'blender[\s\-_]?server',
    r'cadquery[\s\-_]?mcp', r'cadcamfun',
    r'fusion[\s\-_]?360', r'eyeshot[\s\-_]?cad',
    r'rhino[\s\-_]?mcp', r'golem[\s\-_]?3dmcp',
    # 仿真/CAE
    r'isaac[\s\-_]?sim', r'isaac[\s\-_]?lab', r'gazebo[\s\-_]?mcp',
    r'pybullet[\s\-_]?mcp', r'mujoco[\s\-_]?mcp',
    r'comsol[\s\-_]?mcp', r'energyplus',
    r'mlagents[\s\-_]?mcp', r'ardupilot[\s\-_]?sandbox',
    # 纯软件工具
    r'web[\s\-_]?fetch', r'go[\s\-_]?web[\s\-_]?fetch',
    r'lordicon[\s\-_]?mcp', r'shadcn[\s\-_]?ui',
    r'proptech[\s\-_]?mcp', r'roster[\s\-_]?generator',
    r'undesirables[\s\-_]?mcp', r'barf[\s\-_]?mcp',
    r'ssh[\s\-_]?mcp', r'cnc[\s\-_]?youtube',
    r'dart[\s\-_]?mcp', r'metoro[\s\-_]?mcp',
    r'mapbox[\s\-_]?mcp', r'crabcut',
    r'vectorize[\s\-_]?mcp', r'hardware[\s\-_]?store',
    r'picotool', r'MCPi', r'pybullet',
    r'particle[\s\-_]?physics', r'energyatit',
    r'akramiot', r'zta[\s\-_]?mcp', r'fyta[\s\-_]?mcp',
    # 软件框架
    r'kapua[\s\-_]?mcp', r'thingspanel',
    r'omni[\s\-_]?fun', r'harness[\s\-_]?mcp',
    r'ejunz[\s\-_]?mcp', r'integration[\s\-_]?app',
    r'membrane[\s\-_]?mcp', r'uniquejava[\s\-_]?hello[\s\-_]?world',
    r'mimisukeMaster[\s\-_]?python[\s\-_]?mcp',
    # 非硬件传感器
    r'ambient[\s\-_]?sensor', r'sensorbio',
    r'framegrab',
    # 纯软件ROS工具
    r'ros2[\s\-_]?logs', r'ros[\s\-_]?bridge[\s\-_]?mcp',
    r'nav2[\s\-_]?mcp[\s\-_]?server',
    r'perception[\s\-_]?mcp', r'cv[\s\-_]?mcp',
    r'langgraph[\s\-_]?mcp',
    # 其他
    r'openbci', r'lidarr',
    r'studio[\s\-_]?5000', r'tia[\s\-_]?portal',
    r'br[\s\-_]?automation[\s\-_]?pvi',
    r'opc[\s\-_]?ua', r'mdbus',
    r'safie[\s\-_]?api',
    r'buttplug',
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
    r'kubja[\s\-_]?ros2[\s\-_]?turtlebot',
    r'ranch[\s\-_]?hand[\s\-_]?robotics',
    r'poly[\s\-_]?mcp',
    r'lpigeon[\s\-_]?unitree',
    r'waltercoan[\s\-_]?daprday2025',
    r'GetSensr[\s\-_]?io',
    r'jastill[\s\-_]?Sensor',
    r'ThomasGomezWagner[\s\-_]?cameras',
    r'jotamunz[\s\-_]?SensorReading',
    r'apicov[\s\-_]?ambient',
    r'jmdaly[\s\-_]?ouster[\s\-_]?lidar',
    r'abl030[\s\-_]?lidarr',
    r'AndreiT0[\s\-_]?IoT[\s\-_]?Edge',
    r'aws[\s\-_]?samples[\s\-_]?Amazon[\s\-_]?IoT',
    r'shahidhustles[\s\-_]?Arduino',
    r'pparth230[\s\-_]?Arduino',
    r'gn00191283[\s\-_]?cnc',
    r'codeandcloud[\s\-_]?cnc',
    r'agentled[\s\-_]?mcp',
    r'redciprianpater[\s\-_]?robotics',
    r'darshan[\s\-_]?kt[\s\-_]?turtlebot',
    r'darshankt[\s\-_]?turtle',
    r'lwsinclair[\s\-_]?akramiot',
    r'keiner[\s\-_]?2006[\s\-_]?hardware',
    r'Ranch[\s\-_]?Hand[\s\-_]?Robotics',
    r'lpigeon[\s\-_]?unitree',
    r'kmanditereza[\s\-_]?industrial[\s\-_]?data',
    r'daniguzman32[\s\-_]?industrial',
    r'gtoff[\s\-_]?moveit',
    r'kouichiume[\s\-_]?llm[\s\-_]?mcp[\s\-_]?ros2',
    r'hirasawagen[\s\-_]?mcp[\s\-_]?ros2',
    r'darshankt[\s\-_]?turtle[\s\-_]?mcp[\s\-_]?ros2',
    r'darshan[\s\-_]?kt[\s\-_]?turtle[\s\-_]?mcp[\s\-_]?ros2',
    r'gavindev14[\s\-_]?mcp[\s\-_]?server[\s\-_]?ros',
    r'PATRAKECU[\s\-_]?MCP[\s\-_]?Server',
    r'hfujikawa77[\s\-_]?ardupilot',
    r'Nodeblue[\s\-_]?AI[\s\-_]?bridge',
    r'Nodeblue[\s\-_]?AI[\s\-_]?studio',
    r'ggw[\s\-_]?yamabato[\s\-_]?mcp[\s\-_]?unity',
    r'ilevin1[\s\-_]?isaacglevin',
    r'smslavin[\s\-_]?mcp[\s\-_]?servers',
    r'ccutcliff[\s\-_]?MCPi',
    r'vinupalackal[\s\-_]?lightweight',
    r'es617[\s\-_]?ble',
    r'phamhoanggg[\s\-_]?MCP[\s\-_]?Server[\s\-_]?Unity',
    r'gingerol[\s\-_]?vhcilab[\s\-_]?unreal',
    r'WENZHELIN[\s\-_]?BlenderGNMCP',
    r'Gyan[\s\-_]?max[\s\-_]?MCP[\s\-_]?Server[\s\-_]?blender',
    r'webita[\s\-_]?blender[\s\-_]?codex',
    r'CaseyRo[\s\-_]?mcp[\s\-_]?lordicon',
    r'AccelByte[\s\-_]?unreal[\s\-_]?sdk',
    r'devgabrielsborges[\s\-_]?bullet',
    r'juijunnarkar[\s\-_]?COMSOL',
    r'lkysyzxz[\s\-_]?MCPForUnity',
    r'harness[\s\-_]?mcp',
    r'hirasawagen[\s\-_]?mcp[\s\-_]?ros2',
    r'darshankt[\s\-_]?turtle[\s\-_]?mcp[\s\-_]?ros2',
    r'darshan[\s\-_]?kt[\s\-_]?turtle[\s\-_]?mcp[\s\-_]?ros2',
    r'kouichiume[\s\-_]?llm[\s\-_]?mcp[\s\-_]?ros2',
    r'gavindev14[\s\-_]?mcp[\s\-_]?server[\s\-_]?ros',
    r'daniguzman32[\s\-_]?mcp[\s\-_]?server[\s\-_]?industrial',
    r'kmanditereza[\s\-_]?mcp[\s\-_]?server[\s\-_]?industrial[\s\-_]?data',
    r'gtoff[\s\-_]?moveit',
    r'es617[\s\-_]?ble',
    r'ilevin1[\s\-_]?isaacglevin',
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

def classify_item(item):
    """返回: 'keep', 'delete', 'review'"""
    name = item.get('name', '').lower()
    url = item.get('githubRepoUrl', '').lower()
    text = f'{name} {url}'
    
    # 提取owner和repo用于更精确匹配
    owner_repo = ''
    if 'github.com/' in url:
        parts = url.split('github.com/')[-1].split('/')
        if len(parts) >= 2:
            owner_repo = f'{parts[0]}/{parts[1]}'.lower()
    
    # 1. 先检查白名单（保留）- 检查name、url、owner_repo
    for pattern in KEEP_PATTERNS:
        if re.search(pattern, text) or re.search(pattern, owner_repo):
            return 'keep', f'Whitelist: {pattern}'
    
    # 2. 检查删除规则
    for pattern in DELETE_PATTERNS:
        if re.search(pattern, text):
            return 'delete', f'Delete pattern: {pattern}'
    
    # 3. 默认保留（需要人工review）
    return 'review', 'Needs manual review'

def delete_item(item_id):
    try:
        resp = requests.delete(f'{MCP_ENDPOINT}?id={item_id}', headers=HEADERS, timeout=30)
        return resp.status_code in [200, 201, 204], resp.status_code
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 60)
    print("ROSClaw 第六轮清理 - 最终LLM验证")
    print("=" * 60)
    
    progress = load_progress()
    deleted_ids = set(progress['deleted_ids'])
    
    items = get_all_items()
    print(f"\n当前网站: {len(items)} 个MCP包")
    
    # 分类
    to_delete = []
    to_keep = []
    to_review = []
    
    for item in items:
        if item['id'] in deleted_ids:
            continue
        
        result, reason = classify_item(item)
        item['_result'] = result
        item['_reason'] = reason
        
        if result == 'delete':
            to_delete.append(item)
        elif result == 'keep':
            to_keep.append(item)
        else:
            to_review.append(item)
    
    print(f"\n分类结果:")
    print(f"  ✅ 保留（白名单）: {len(to_keep)}")
    print(f"  ❌ 删除（非硬件）: {len(to_delete)}")
    print(f"  ⚠️  需人工确认: {len(to_review)}")
    
    # 打印待删除样本
    if to_delete:
        print(f"\n=== 待删除样本（前20个）===")
        for item in to_delete[:20]:
            print(f"  ❌ {item['name']} | {item.get('githubRepoUrl', '')}")
        if len(to_delete) > 20:
            print(f"  ... 还有 {len(to_delete)-20} 个")
    
    # 打印保留样本
    if to_keep:
        print(f"\n=== 保留样本 ===")
        for item in to_keep[:20]:
            print(f"  ✅ {item['name']} | {item.get('githubRepoUrl', '')}")
        if len(to_keep) > 20:
            print(f"  ... 还有 {len(to_keep)-20} 个")
    
    # 打印需确认样本
    if to_review:
        print(f"\n=== 需人工确认样本 ===")
        for item in to_review[:20]:
            print(f"  ⚠️  {item['name']} | {item.get('githubRepoUrl', '')}")
        if len(to_review) > 20:
            print(f"  ... 还有 {len(to_review)-20} 个")
    
    # 询问是否执行删除
    print(f"\n{'='*60}")
    print(f"准备删除 {len(to_delete)} 个非硬件MCP项目")
    print(f"保留 {len(to_keep)} 个物理硬件MCP项目")
    print(f"{len(to_review)} 个项目需要人工确认")
    print(f"\n如需执行删除，请运行: python3 delete_round6.py --execute")
    
    # 保存分类报告
    report = {
        'timestamp': datetime.now().isoformat(),
        'total': len(items),
        'keep': [{'name': i['name'], 'url': i.get('githubRepoUrl', ''), 'reason': i['_reason']} for i in to_keep],
        'delete': [{'name': i['name'], 'url': i.get('githubRepoUrl', ''), 'reason': i['_reason']} for i in to_delete],
        'review': [{'name': i['name'], 'url': i.get('githubRepoUrl', ''), 'reason': i['_reason']} for i in to_review],
    }
    with open('round6_classification.json', 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n📄 分类报告已保存: round6_classification.json")

def execute_delete():
    progress = load_progress()
    deleted_ids = set(progress['deleted_ids'])
    
    items = get_all_items()
    to_delete = []
    
    for item in items:
        if item['id'] in deleted_ids:
            continue
        result, _ = classify_item(item)
        if result == 'delete':
            to_delete.append(item)
    
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
    print("第六轮清理完成!")
    print(f"成功: {success}, 失败: {failed}")
    
    remaining = get_all_items()
    print(f"剩余MCP: {len(remaining)}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--execute':
        execute_delete()
    else:
        main()
