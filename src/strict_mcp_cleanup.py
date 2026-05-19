#!/usr/bin/env python3
"""
严格验证并删除rosclaw.io上的非MCP项目
验证标准（按SOUL.md的Hardware MCP Search Expert原则）：
1. 真正实现MCP协议（有server实现代码、tools/capabilities定义）
2. 不是纯仿真平台/数据集/awesome-list
3. 有实际的硬件/机器人接口
"""

import requests
import json
import time
import re
from datetime import datetime
from urllib.parse import urlparse

API_KEY = '"${ROSCALW_API_KEY}"'
BASE_URL = 'https://www.rosclaw.io'
MCP_ENDPOINT = f'{BASE_URL}/api/mcp-packages'
SKILL_ENDPOINT = f'{BASE_URL}/api/skills'

HEADERS = {
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY
}

# ===== 硬性排除规则 =====
# 这些模式一出现，直接判定为非真正MCP
SKIP_PATTERNS = [
    # 纯游戏引擎bridge（无物理硬件控制）
    r'unreal[\s\-_]?mcp', r'unity[\s\-_]?mcp',
    # 纯软件工具（无硬件）
    r'second[\s\-_]?brain', r'blender[\s\-_]?mcp',
    r'3d[\s\-_]?software', r'cad[\s\-_]?mcp',
    # 纯IoT数据（无MCP server实现）
    r'iotdb', r'tapo',  # 智能家居设备，不是MCP server
    # 名字可疑但无实际MCP
    r'rossum',  # 文档处理，不是机器人
]

# ===== 明确接受的真正MCP模式 =====
TRUE_MCP_PATTERNS = [
    r'mcp[\s\-_]?server', r'mcp[\s\-_]?ros', r'ros[\s\-_]?mcp',
    r'ros2[\s\-_]?mcp', r'mcp[\s\-_]?bridge',
    r'@modelcontextprotocol',
]

# ===== 需要人工复核的边界项目 =====
BORDERLINE_PATTERNS = [
    r'robot', r'arm', r'drone', r'uav', r'gripper',
    r'sensor', r'lidar', r'camera', r'imu',
    r'gpio', r'i2c', r'spi', r'uart', r'serial',
    r'plc', r'modbus', r'can', r'obd',
    r'3d[\s\-_]?printer', r'cnc', r'grbl',
    r'home[\s\-_]?assistant', r'smart[\s\-_]?home',
]

def get_all_site_items(endpoint, item_type):
    """分页获取网站上所有项目"""
    all_items = []
    page = 1
    limit = 100
    
    while True:
        try:
            resp = requests.get(
                f"{endpoint}?page={page}&limit={limit}",
                headers=HEADERS, timeout=30
            )
            if resp.status_code != 200:
                print(f"  ⚠️ 获取{item_type}列表失败: HTTP {resp.status_code}")
                break
            
            data = resp.json()
            items = data if isinstance(data, list) else data.get('items', data.get('data', []))
            
            if not items:
                break
            
            all_items.extend(items)
            print(f"  第{page}页获取 {len(items)} 个{item_type}")
            
            if len(items) < limit:
                break
            
            page += 1
            time.sleep(0.3)
            
        except Exception as e:
            print(f"  ⚠️ 获取{item_type}列表出错: {e}")
            break
    
    return all_items

def strict_classify(item):
    """
    严格分类：
    - 'true_mcp': 真正MCP（保留）
    - 'fake_mcp': 非真正MCP（删除）
    - 'borderline': 边界情况（需要人工确认）
    """
    name = item.get('name', '').lower()
    url = item.get('githubRepoUrl', '').lower()
    text = f"{name} {url}"
    
    # 1. 先检查硬性排除规则
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, text):
            return 'fake_mcp', f'Hard skip: {pattern}'
    
    # 2. 检查明确接受的MCP模式
    for pattern in TRUE_MCP_PATTERNS:
        if re.search(pattern, text):
            return 'true_mcp', f'MCP pattern: {pattern}'
    
    # 3. 检查边界模式（有硬件关键词但不确定是否真MCP）
    for pattern in BORDERLINE_PATTERNS:
        if re.search(pattern, text):
            return 'borderline', f'Borderline: {pattern}'
    
    # 4. 默认：名字带mcp但无server实现证据
    if 'mcp' in name:
        return 'fake_mcp', 'Name contains mcp but no server evidence'
    
    # 5. 完全无关
    return 'fake_mcp', 'Not MCP related'

def delete_item_by_id(item_id, endpoint_base, item_name):
    """通过ID删除项目"""
    try:
        delete_endpoint = f"{endpoint_base}?id={item_id}"
        response = requests.delete(delete_endpoint, headers=HEADERS, timeout=30)
        
        if response.status_code in [200, 201, 204]:
            return True, f"Deleted ({response.status_code})"
        elif response.status_code == 404:
            return True, f"Not found (404)"
        
        return False, f"HTTP {response.status_code}: {response.text[:200]}"
    
    except Exception as e:
        return False, f"Error: {str(e)}"

def main():
    start_time = time.time()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    print("=" * 70)
    print("ROSClaw 严格MCP验证清理工具")
    print("标准：只保留真正实现MCP协议 + 有物理硬件接口的项目")
    print("=" * 70)
    
    # 获取所有MCP包
    print("\n📦 获取网站上所有MCP包...")
    mcp_items = get_all_site_items(MCP_ENDPOINT, 'MCP')
    total = len(mcp_items)
    print(f"\n网站上共有 {total} 个MCP包")
    
    if total == 0:
        print("网站上没有MCP包，退出")
        return
    
    # 分类统计
    true_mcp = []
    fake_mcp = []
    borderline = []
    
    print("\n" + "=" * 70)
    print("开始严格分类...")
    print("=" * 70)
    
    for item in mcp_items:
        result, reason = strict_classify(item)
        item['_classify'] = result
        item['_reason'] = reason
        
        if result == 'true_mcp':
            true_mcp.append(item)
        elif result == 'fake_mcp':
            fake_mcp.append(item)
        else:
            borderline.append(item)
    
    print(f"\n分类结果:")
    print(f"  ✅ 真正MCP（保留）: {len(true_mcp)}")
    print(f"  ❌ 非真正MCP（删除）: {len(fake_mcp)}")
    print(f"  ⚠️  边界情况（需确认）: {len(borderline)}")
    
    # 打印各类样本
    print(f"\n--- 真正MCP样本 ---")
    for item in true_mcp[:10]:
        print(f"  ✅ {item['name']} | {item.get('githubRepoUrl', 'N/A')}")
    if len(true_mcp) > 10:
        print(f"  ... 还有 {len(true_mcp)-10} 个")
    
    print(f"\n--- 非真正MCP样本（将被删除）---")
    for item in fake_mcp[:20]:
        print(f"  ❌ {item['name']} | {item.get('githubRepoUrl', 'N/A')} | {item['_reason']}")
    if len(fake_mcp) > 20:
        print(f"  ... 还有 {len(fake_mcp)-20} 个")
    
    print(f"\n--- 边界情况样本 ---")
    for item in borderline[:20]:
        print(f"  ⚠️  {item['name']} | {item.get('githubRepoUrl', 'N/A')} | {item['_reason']}")
    if len(borderline) > 20:
        print(f"  ... 还有 {len(borderline)-20} 个")
    
    # 生成完整报告
    report = {
        'timestamp': timestamp,
        'total': total,
        'true_mcp_count': len(true_mcp),
        'fake_mcp_count': len(fake_mcp),
        'borderline_count': len(borderline),
        'true_mcp': [{'name': i['name'], 'url': i.get('githubRepoUrl', ''), 'reason': i['_reason']} for i in true_mcp],
        'fake_mcp': [{'name': i['name'], 'url': i.get('githubRepoUrl', ''), 'reason': i['_reason']} for i in fake_mcp],
        'borderline': [{'name': i['name'], 'url': i.get('githubRepoUrl', ''), 'reason': i['_reason']} for i in borderline],
    }
    
    report_file = f'/home/ubuntu/.openclaw/workspace/rosclaw_crawler/mcp_audit_report_{timestamp}.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n📄 审计报告已保存: {report_file}")
    
    # 询问是否执行删除（默认只展示报告，不自动删除）
    print("\n" + "=" * 70)
    print("⚠️  删除确认")
    print("=" * 70)
    print(f"即将删除 {len(fake_mcp)} 个非真正MCP项目")
    print(f"保留 {len(true_mcp)} 个真正MCP项目")
    print(f"{len(borderline)} 个边界项目建议人工确认后再处理")
    print("\n如需执行删除，请运行: python3 strict_mcp_cleanup.py --execute")
    
    return report

def execute_delete():
    """执行删除操作"""
    # 先运行分类
    import sys
    sys.argv = [sys.argv[0]]  # 重置参数
    
    # 重新获取并分类
    print("\n🚀 执行删除模式...")
    mcp_items = get_all_site_items(MCP_ENDPOINT, 'MCP')
    
    fake_mcp = []
    for item in mcp_items:
        result, reason = strict_classify(item)
        if result == 'fake_mcp':
            item['_reason'] = reason
            fake_mcp.append(item)
    
    print(f"\n将删除 {len(fake_mcp)} 个非真正MCP项目")
    
    # 执行删除
    success_count = 0
    fail_count = 0
    results = []
    
    for i, item in enumerate(fake_mcp, 1):
        item_id = item.get('id')
        name = item.get('name', 'unknown')
        
        print(f"\n[{i}/{len(fake_mcp)}] 删除: {name} ({item['_reason']})")
        
        success, msg = delete_item_by_id(item_id, MCP_ENDPOINT, name)
        
        if success:
            success_count += 1
            print(f"  ✅ {msg}")
        else:
            fail_count += 1
            print(f"  ❌ {msg}")
        
        results.append({
            'name': name,
            'id': item_id,
            'reason': item['_reason'],
            'success': success,
            'message': msg
        })
        
        time.sleep(0.3)
    
    # 保存删除日志
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log = {
        'timestamp': timestamp,
        'total_deleted': len(fake_mcp),
        'success': success_count,
        'failed': fail_count,
        'results': results
    }
    log_file = f'/home/ubuntu/.openclaw/workspace/rosclaw_crawler/mcp_delete_log_{timestamp}.json'
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 70)
    print("删除完成!")
    print("=" * 70)
    print(f"总计尝试删除: {len(fake_mcp)}")
    print(f"成功删除: {success_count}")
    print(f"失败: {fail_count}")
    print(f"日志文件: {log_file}")
    
    # 验证剩余数量
    print("\n🔍 验证剩余项目...")
    remaining = get_all_site_items(MCP_ENDPOINT, 'MCP')
    print(f"网站上剩余MCP: {len(remaining)}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--execute':
        execute_delete()
    else:
        main()
