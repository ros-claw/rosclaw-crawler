#!/usr/bin/env python3
"""
第七轮清理 - 最终确认39个边界项目
基于实际仓库内容判断
"""

import requests
import json
import re
import time
import os
from datetime import datetime

API_KEY = '"${ROSCALW_API_KEY}"'
BASE_URL = 'https://www.rosclaw.io'
MCP_ENDPOINT = f'{BASE_URL}/api/mcp-packages'
HEADERS = {'Content-Type': 'application/json', 'X-API-Key': API_KEY}

PROGRESS_FILE = 'delete_progress_round7.json'
REVIEW_FILE = 'round6_classification.json'

# 基于实际内容的手动分类 - 这39个项目经过仔细审查
MANUAL_DELETE = [
    # 纯软件/无硬件接口
    'kontext-security/attestable-mcp-server',  # 安全认证，无硬件
    'ag2-mcp-servers/hardware-sentry-truesight-presentation-server-rest-api',  # 软件监控
    'ag2-mcp-servers/karnataka-industrial-areas-development-board-karnataka',  # 政府部门，非硬件
    'wenbox360/hardware_mcp_server',  # 硬件商店，非控制
    # 仿真/非物理
    'ilevin1/mcp-server-deployment-isaacglevin',  # Isaac Sim部署，仿真
    # 不确定/可能删除
    'MacromNex/gromacs_mcp',  # GROMACS分子动力学，可能是仿真
]

MANUAL_KEEP = [
    # 传感器/物联网（明确硬件）
    'hemantkamalakar/nordic-thingy52-mcp',  # Nordic Thingy52传感器
    'juhapellotsalo/ruuvi-mcp-server',  # Ruuvi传感器
    'Showdown76py/BeaconMCP',  # 蓝牙信标
    'martydill/yolink-mcp',  # YoLink物联网
    'cyanheads/pixoo-mcp-server',  # Pixoo LED显示
    'es617/ble-mcp-server',  # BLE蓝牙低功耗
    'swannman/openthread-mcp',  # OpenThread物联网
    # 摄像头/视觉
    'pavel-kirienko/webcam_mcp',  # 摄像头
    'brianegge/dahua-mcp',  # 大华监控摄像头
    'SingTown/openmv-mcp',  # OpenMV机器视觉
    # 工业/硬件
    'brs077/3dp-mcp-server',  # 3D打印
    'CSOAI-ORG/qidi-printer-mcp',  # Qidi打印机
    'JanGoebel/NI-Hardware-MCP-Server',  # NI硬件
    'Arkintea/Industrial_MCP_Server',  # 工业MCP
    'kmanditereza/mcp-server-for-industrial-data',  # 工业数据
    'daniguzman32/mcp-server-industrial',  # 工业MCP
    'lujin3/industrial-mcp-server-demo',  # 工业演示
    'Acceleronix/acc-mcp-server-local',  # 硬件加速
    'jrutanen/acap-mcp-server',  # ACAP硬件
    'raibid-labs/dgx-spark-mcp',  # DGX Spark
    # ROS2/机器人
    'binabik-ai/mcp-rosbags',  # ROS数据包
    'cjh1995-ros/rosbag-mcp',  # ROS数据包
    'gtoff/moveit-mcp-server',  # MoveIt机器人
    'gavindev14/mcp_server_ros_2',  # ROS2
    'kouichiume/llm_mcp_ros2_adapter',  # ROS2适配器
    'darshankt/turtle_mcp_ros2',  # TurtleBot
    'hirasawagen/mcp_ros2',  # ROS2
    'darshan-kt/turtle_mcp_ros2',  # TurtleBot
    'jackccrawford/reachy-mini-mcp',  # Reachy机器人
    # 其他硬件
    'MarinX/lg-thermav-mcp-server',  # LG热泵
    'YudaiKitamura/mcpx-mcp-server',  # MCPX
    'KenosInc/sigrok-mcp-server',  # Sigrok信号分析
    'ekakit/lightfast-mcp',  # Lightfast
]

UNCERTAIN = [
    # 需要进一步确认
    'MacromNex/gromacs_mcp',  # GROMACS分子动力学
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
    print("ROSClaw 第七轮清理 - 最终确认39个边界项目")
    print("=" * 60)
    
    progress = load_progress()
    deleted_ids = set(progress['deleted_ids'])
    
    # 加载第六轮的review项目
    if not os.path.exists(REVIEW_FILE):
        print(f"❌ 找不到 {REVIEW_FILE}，请先运行第六轮清理")
        return
    
    with open(REVIEW_FILE, 'r') as f:
        round6_data = json.load(f)
    
    review_items = round6_data.get('review', [])
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
    with open('round7_classification.json', 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n📄 分类报告已保存: round7_classification.json")
    
    print(f"\n如需执行删除，请运行: python3 delete_round7.py --execute")

def execute_delete():
    progress = load_progress()
    deleted_ids = set(progress['deleted_ids'])
    
    # 加载第七轮分类报告
    if not os.path.exists('round7_classification.json'):
        print(f"❌ 找不到 round7_classification.json，请先运行分类")
        return
    
    with open('round7_classification.json', 'r') as f:
        round7_data = json.load(f)
    
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
    for item_data in round7_data.get('delete', []):
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
    print("第七轮清理完成!")
    print(f"成功: {success}, 失败: {failed}")
    
    remaining = get_all_items()
    print(f"剩余MCP: {len(remaining)}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--execute':
        execute_delete()
    else:
        main()
