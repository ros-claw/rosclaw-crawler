#!/usr/bin/env python3
"""
ROSClaw Strict Filter - 严格筛选rosclaw.io相关项目

核心原则：
1. 必须是 MCP Server 或 Agent Skill 的形式
2. 必须与具身智能/物理AI/机器人直接相关
3. 必须能被AI Agent直接调用/使用

明确拒绝（只要满足一项就拒绝）：
- 纯软件工具（不含物理交互）
- 办公/文档/营销/B2B类
- 教程/列表/合集/awesome-list
- 纯AI聊天/助手（不含机器人）
- 通用开发工具/框架（不含Agent接口）
- 纯算法库/数据集/模型权重
- 纯硬件设计（不含Agent接口）
- 仿真平台本身（不是MCP/Skill）
- 低质量/玩具/测试项目
- 非机器人相关的IoT/智能家居
"""

import re

# ===== 硬性排除模式 =====
# 这些模式一出现，直接判定为不相关
HARD_EXCLUDE_PATTERNS = [
    # 纯软件/办公/营销
    r'awesome[-_]', r'prompt', r'chatgpt', r'marketing', r'seo', r'crm',
    r'email', r'slack', r'discord', r'notion', r'trello',
    # 纯AI助手/聊天（非机器人）
    r'personal\s+ai\s+assistant', r'ai\s+assistant\s+any\s+os',  # clawdis/openclaw generic
    # 教程/列表
    r'awesome[-_]', r'paper[-_]list', r'survey',
    r'handbook', r'book', r'tutorial', r'guide',
    # 通用开发工具
    r'electron', r'vscode', r'ide', r'editor',
    # B2B/商业
    r'b2b', r'commercial', r'enterprise\s+sales',
    # 低质量/测试
    r'test[-_]', r'demo[-_]', r'example[-_]', r'exploring',
    r'generated\s+by\s+mcp\.ag2\.ai',  # 自动生成的低质量MCP
    # 非机器人IoT
    r'smart\s+home', r'home\s+assistant', r'heat\s+pump',  # 智能家居
    r'motor\s+vehicle\s+department',  # 政府部门
    r'ledger\s+hardware\s+wallet',  # 加密货币
    r'youtube', r'video',  # 媒体
]

# ===== 明确接受的模式 =====
# 这些模式表明项目是真正的MCP Server或Agent Skill
TRUE_MCP_PATTERNS = [
    r'mcp[-_]?server', r'mcp[-_]?bridge', r'mcp[-_]?ros', r'ros[-_]?mcp',
    r'ros2[-_]?mcp', r'ros[-_]?mcp[-_]?server',
    r'@modelcontextprotocol',
]

TRUE_SKILL_PATTERNS = [
    r'skill\.md', r'claude[-_]?skill', r'agent[-_]?skill',
    r'openclaw[-_]?skill', r'\.claude',
]

# ===== 宽松的MCP检测 =====
# 如果名字中包含mcp且描述中提到机器人/硬件，也认为是MCP
MCP_LOOSE_INDICATORS = [
    'mcp', 'model context protocol',
]

# 描述中表明是MCP server的证据
MCP_DESCRIPTION_EVIDENCE = [
    'mcp server', 'model context protocol server',
    'mcp bridge', 'mcp client',
    'connect ai', 'llm agent', 'ai agent',
    'claude', 'gpt', 'language model',
]

# 描述中表明是Agent Skill的证据
SKILL_DESCRIPTION_EVIDENCE = [
    'skill.md', 'agent skill', 'claude skill',
    'openclaw skill', 'skill for',
    '.claude directory', 'claude code',
]

# ===== 具身智能相关关键词 =====
EMBODIED_KEYWORDS = [
    'robot', 'robotics', 'ros', 'ros2', 'manipulator', 'arm', 'gripper',
    'humanoid', 'quadruped', 'legged', 'mobile robot', 'drone', 'uav',
    'autonomous', 'navigation', 'slam', 'lidar', 'depth camera',
    'mujoco', 'isaac sim', 'gazebo', 'pybullet', 'simulation',
    'teleoperation', 'teleop', 'imitation learning', 'reinforcement learning',
    'vla', 'vision language action', 'diffusion policy', 'act',
    'kinematics', 'dynamics', 'motion planning', 'trajectory',
    'servo', 'motor', 'encoder', 'sensor', 'imu', 'force sensor',
    'plc', 'modbus', 'opc ua', 'industrial', 'cnc', '3d printer',
    'bambu', 'klipper', 'prus', 'octoprint',
    'arduino', 'esp32', 'raspberry pi', 'jetson', 'embedded',
    'unitree', 'franka', 'ur5', 'ur10', 'universal robot',
    'reachy', 'turtlebot', 'so-101', 'so-arm100',
    'mavlink', 'px4', 'ardupilot',
]

# ===== 仿真平台本身（应排除，除非有MCP/Skill接口）=====
SIMULATION_PLATFORMS = [
    'habitat-sim', 'habitat-lab', 'isaaclab', 'isaac sim',
    'gymnasium', 'dm_control', 'roboschool', 'genesis',
]

# ===== 纯算法库/模型（应排除，除非有MCP/Skill接口）=====
PURE_ALGO_LIBS = [
    'stable-baselines', 'cleanrl', 'elegantrl', 'rsl_rl',
    'roboticsdiffusiontransformer', 'open-pi-zero', 'psi0',
    'gr00t', 'act-plus-plus', 'mobile-aloha', 'aloha',
    'navrl', 'asap',
]

# ===== 纯硬件项目（应排除，除非有MCP/Skill接口）=====
PURE_HARDWARE = [
    'openarm', 'dummy-robot', 'spotmicro', 'open_duck_mini',
    'low_cost_robot', 'xlerobot',
]


def strict_classify(name: str, description: str, url: str, item_type: str = None) -> tuple:
    """
    严格分类项目
    返回: (decision, reason, confidence)
    decision: 'keep', 'remove', 'review'
    """
    text = f"{name} {description or ''} {url or ''}".lower()
    name_lower = name.lower()
    desc_lower = (description or '').lower()

    # 1. 先检查硬性排除
    for pattern in HARD_EXCLUDE_PATTERNS:
        if re.search(pattern, text):
            return 'remove', f'Hard exclude: matches {pattern}', 'high'

    # 2. 检查是否是纯仿真平台
    for platform in SIMULATION_PLATFORMS:
        if platform in name_lower:
            # 只有当明确提到MCP/Skill时才保留
            has_mcp_skill = any(p in text for p in TRUE_MCP_PATTERNS + TRUE_SKILL_PATTERNS)
            if not has_mcp_skill:
                return 'remove', f'Pure simulation platform without MCP/Skill interface: {platform}', 'high'

    # 3. 检查是否是纯算法库/模型
    for algo in PURE_ALGO_LIBS:
        if algo in name_lower:
            has_mcp_skill = any(p in text for p in TRUE_MCP_PATTERNS + TRUE_SKILL_PATTERNS)
            if not has_mcp_skill:
                return 'remove', f'Pure algorithm/model without MCP/Skill interface: {algo}', 'high'

    # 4. 检查是否是纯硬件项目
    for hw in PURE_HARDWARE:
        if hw in name_lower:
            has_mcp_skill = any(p in text for p in TRUE_MCP_PATTERNS + TRUE_SKILL_PATTERNS)
            if not has_mcp_skill:
                return 'remove', f'Pure hardware project without MCP/Skill interface: {hw}', 'high'

    # 5. 检查是否明确是MCP Server（严格模式）
    is_true_mcp = any(re.search(p, text) for p in TRUE_MCP_PATTERNS)
    is_true_skill = any(re.search(p, text) for p in TRUE_SKILL_PATTERNS)

    # 5b. 宽松模式：名字中有mcp且描述中有MCP相关证据
    has_mcp_in_name = 'mcp' in name_lower
    has_mcp_evidence = any(e in desc_lower for e in MCP_DESCRIPTION_EVIDENCE)
    has_skill_evidence = any(e in desc_lower for e in SKILL_DESCRIPTION_EVIDENCE)

    # 5c. 特殊判断：名字中有mcp且与具身智能强相关（3D打印、无人机、机器人、工业控制）
    strong_embodied_indicators = [
        '3d printer', '3d print', 'bambu', 'klipper', 'prus', 'octoprint', 'orca',
        'drone', 'uav', 'mavlink', 'px4', 'ardupilot', 'tello',
        'robot', 'ros', 'ros2', 'manipulator', 'arm', 'gripper',
        'humanoid', 'quadruped', 'legged', 'turtlebot',
        'unitree', 'franka', 'ur5', 'ur10', 'universal robot',
        'reachy', 'so-101', 'so-arm100',
        'plc', 'modbus', 'opc ua', 'opc-ua', 'opcua', 'industrial',
        'cnc', 'servo', 'motor', 'encoder', 'sensor', 'lidar',
        'arduino', 'esp32', 'raspberry pi', 'jetson',
        'mujoco', 'isaac sim', 'isaac-sim', 'gazebo', 'pybullet',
        'slam', 'navigation', 'teleoperation', 'teleop',
    ]
    has_strong_embodied = any(ind in text for ind in strong_embodied_indicators)

    # 5d. ros-claw官方项目直接信任
    is_rosclaw_official = 'ros-claw' in name_lower or 'ros-claw' in (url or '').lower()

    is_loose_mcp = has_mcp_in_name and (has_mcp_evidence or has_strong_embodied)
    is_loose_skill = has_skill_evidence

    is_any_mcp = is_true_mcp or is_loose_mcp
    is_any_skill = is_true_skill or is_loose_skill

    # 6. 检查具身智能相关性
    embodied_score = 0
    for kw in EMBODIED_KEYWORDS:
        if kw in text:
            embodied_score += 1

    # 7. 决策逻辑
    if is_rosclaw_official:
        return 'keep', 'ROSClaw official project', 'high'

    if is_any_mcp or is_any_skill:
        if embodied_score >= 2 or has_strong_embodied:
            return 'keep', f'{"MCP" if is_any_mcp else "Skill"} with embodied relevance (score={embodied_score})', 'high'
        elif embodied_score >= 1:
            return 'review', f'{"MCP" if is_any_mcp else "Skill"} with weak embodied relevance (score={embodied_score})', 'medium'
        else:
            return 'remove', f'{"MCP" if is_any_mcp else "Skill"} but no embodied relevance', 'high'

    # 8. 如果没有MCP/Skill标识，但描述中有明确的Agent+物理交互
    if 'agent' in text and embodied_score >= 3:
        return 'review', f'Possible embodied agent project (score={embodied_score})', 'medium'

    # 9. 默认排除
    return 'remove', f'Not a recognized MCP Server or Agent Skill (embodied_score={embodied_score})', 'high'


def batch_classify(items: list) -> dict:
    """批量分类项目"""
    results = {'keep': [], 'remove': [], 'review': []}
    for item in items:
        name = item.get('name', '')
        desc = item.get('description', '')
        url = item.get('githubRepoUrl', '') or item.get('repo_url', '')
        item_type = item.get('type', '')

        decision, reason, confidence = strict_classify(name, desc, url, item_type)
        results[decision].append({
            **item,
            '_decision': decision,
            '_reason': reason,
            '_confidence': confidence,
        })
    return results


if __name__ == '__main__':
    # Test with known examples
    test_cases = [
        {'name': 'dbwls99706/ros2-engineering-skills',
         'description': 'Agent skill for production-grade ROS 2 development. Progressive-disclosure SKILL.md',
         'githubRepoUrl': 'https://github.com/dbwls99706/ros2-engineering-skills'},
        {'name': 'enactic/openarm',
         'description': 'A fully open-source humanoid arm for physical AI research',
         'githubRepoUrl': 'https://github.com/enactic/openarm'},
        {'name': 'moveit/moveit2',
         'description': 'MoveIt for ROS 2',
         'githubRepoUrl': 'https://github.com/moveit/moveit2'},
        {'name': 'robotmcp/ros-mcp-server',
         'description': 'Connect AI models like Claude & GPT with robots using MCP and ROS.',
         'githubRepoUrl': 'https://github.com/robotmcp/ros-mcp-server'},
        {'name': 'ag2-mcp-servers/motor-vehicle-department-odisha',
         'description': 'MCP Server generated by mcp.ag2.ai',
         'githubRepoUrl': 'https://github.com/ag2-mcp-servers/motor-vehicle-department-odisha'},
    ]

    print("=" * 80)
    print("ROSClaw Strict Filter Test")
    print("=" * 80)
    for item in test_cases:
        decision, reason, confidence = strict_classify(
            item['name'], item['description'], item['githubRepoUrl']
        )
        status = "✅ KEEP" if decision == 'keep' else "❌ REMOVE" if decision == 'remove' else "⚠️ REVIEW"
        print(f"\n{status} | {confidence}")
        print(f"  Name: {item['name']}")
        print(f"  Reason: {reason}")
