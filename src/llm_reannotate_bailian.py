#!/usr/bin/env python3
"""
ROSClaw LLM Re-Annotation Pipeline
使用阿里百炼 Qwen3.5-plus 重新标注所有数据
废弃旧标注，按ROSClaw生态需求重新评分

API: 阿里百炼 bailian
模型: qwen3.5-plus
Base URL: https://dashscope.aliyuncs.com/compatible-mode/v1
"""

import os
import sys
import json
import sqlite3
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# ============== 配置 ==============
API_KEY = ""${DEEPSEEK_API_KEY}""
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.5-plus"
BATCH_SIZE = 10  # 每批处理数量
MAX_WORKERS = 2  # 降低并发避免限流
REQUEST_TIMEOUT = 120  # 增加超时时间
API_RETRY_DELAY = 5  # 重试间隔

# ROSClaw生态核心关键词（用于Prompt和评分权重）
ROSCLAW_KEYWORDS = {
    "embodied_ai": [
        "embodied ai", "physical ai", "具身智能", "物理AI",
        "robotics", "机器人", "robot", "humanoid", "人形机器人",
        "manipulator", "机械臂", "dexterous hand", "灵巧手",
        "bipedal", "双足", "quadruped", "四足", "mobile robot", "移动机器人",
        "teleoperation", "遥操作", "human-robot interaction", "人机交互"
    ],
    "vla_vln": [
        "vla", "vision language action", "视觉语言动作",
        "vln", "vision language navigation", "视觉语言导航",
        "world model", "世界模型", "foundation model robotics"
    ],
    "simulation": [
        "isaac sim", "nvidia isaac", "mujoco", "gazebo", "pybullet",
        "sim-to-real", "simulation", "仿真", "digital twin", "数字孪生",
        "newton physics", "mjlab"
    ],
    "ros": [
        "ros", "ros2", "robot operating system", "dds", "middleware"
    ],
    "perception": [
        "slam", "computer vision", "3d reconstruction", "nerf", "3dgs",
        "3d gaussian splatting", "sensor fusion", "depth estimation",
        "pose estimation", "spatial intelligence", "空间智能",
        "lidar", "camera calibration", "视觉感知"
    ],
    "control": [
        "reinforcement learning", "rl", "强化学习",
        "imitation learning", "模仿学习", "behavior cloning",
        "act", "action chunking", "diffusion policy",
        "kinematics", "dynamics", "kinodynamic", "运动学", "动力学",
        "mpc", "model predictive control", "wbc", "whole body control",
        "trajectory optimization", "轨迹优化"
    ],
    "hardware": [
        "jetson", "raspberry pi", "embedded", "嵌入式",
        "microcontroller", "mcu", "plc", "servo", "motor control",
        "gripper", "end effector", "force sensor", "imu"
    ],
    "industrial": [
        "industrial automation", "工业自动化", "factory automation",
        "smart manufacturing", "智能制造", "industry 4.0", "工业4.0"
    ]
}

@dataclass
class LLMAnnotation:
    """LLM标注结果"""
    summary: str  # 详细总结
    relevance_score: int  # 0-100 与ROSClaw生态的相关度
    category: str  # 分类
    subcategory: str  # 子分类
    robot_types: List[str]  # 支持的机器人类型
    tags: List[str]  # 标签
    capabilities: List[str]  # 能力/功能列表
    mcp_tools: Optional[List[str]]  # MCP工具列表（仅mcp_server类型）
    hardware_requirements: List[str]  # 硬件需求
    software_dependencies: List[str]  # 软件依赖
    is_rosclaw_native: bool  # 是否原生支持ROSClaw
    confidence: int  # LLM置信度 0-100


def create_annotation_prompt(repo_data: Dict[str, Any]) -> str:
    """创建标注Prompt"""
    
    repo_type = repo_data.get('type', 'unknown')
    name = repo_data.get('name', '')
    description = repo_data.get('description', '')
    url = repo_data.get('repo_url', '')
    stars = repo_data.get('stars', 0)
    
    # 根据类型选择分析模板
    if repo_type == 'mcp_server':
        analysis_template = """
MCP Server Analysis Template:
- What physical/simulation capabilities does this MCP server provide?
- What robot types can it control or interact with?
- What are the specific MCP tools/functions it exposes?
- Is it directly usable for robotics/embodied AI applications?
- Does it integrate with ROS, Isaac Sim, MuJoCo, or other robotics platforms?
"""
    else:  # agent_skill
        analysis_template = """
Agent Skill Analysis Template:
- What physical task or capability does this skill enable?
- What robot types or hardware does it support?
- What are the key actions/capabilities it provides?
- Can it be used across different robot platforms?
- Does it relate to manipulation, navigation, perception, or control?
"""
    
    # ROSClaw生态关键词参考
    keywords_ref = json.dumps(ROSCLAW_KEYWORDS, indent=2, ensure_ascii=False)
    
    prompt = f"""You are an expert evaluator for the ROSClaw Physical AI Ecosystem.

ROSClaw Mission: "Teach Once, Embody Anywhere. Share Skills, Shape Reality."
We are building the world's largest marketplace for Embodied AI and Physical AI skills.

Repository to analyze:
- Type: {repo_type}
- Name: {name}
- URL: {url}
- Stars: {stars}
- Description: {description}

{analysis_template}

ROSClaw Ecosystem Keywords Reference (higher relevance if matching these):
{keywords_ref}

Please provide a detailed analysis in JSON format:
{{
  "summary": "Detailed description of what this project does and its key capabilities (2-3 sentences)",
  "relevance_score": 0-100 integer, higher if directly related to robotics, embodied AI, physical AI, ROS, simulation, control, or hardware,
  "category": "Primary category (e.g., Manipulation, Navigation, Perception, Simulation, Control, Hardware Interface, Tooling, General AI)",
  "subcategory": "More specific subcategory",
  "robot_types": ["List of robot types supported, e.g., 'Universal Robots', 'Humanoid', 'Mobile Robot', 'Robot Arm', 'ANY", "None if not specific"],
  "tags": ["5-10 relevant tags including framework names, algorithms, hardware platforms"],
  "capabilities": ["List of specific capabilities/functions this provides"],
  "mcp_tools": [{"name": "tool_name", "description": "what it does"}] or null if not MCP server,
  "hardware_requirements": ["Required hardware if any, or empty list"],
  "software_dependencies": ["Key dependencies like ROS, ROS2, Isaac Sim, PyTorch, etc."],
  "is_rosclaw_native": true/false - whether this can directly work with ROSClaw OS,
  "confidence": 0-100 integer indicating how confident you are in this analysis
}}

Important scoring guidelines for relevance_score:
- 90-100: Directly implements robotics/embodied AI capabilities (manipulation, navigation, control, perception with real/simulated robots)
- 70-89: Strongly related (simulation platforms, ROS tools, robot learning frameworks, hardware drivers)
- 50-69: Moderately related (general ML for robotics, computer vision that could be used for robots, related tooling)
- 30-49: Weakly related (general AI/ML tools that could theoretically be applied to robotics)
- 0-29: Not relevant (web apps, general software tools, unrelated to physical AI)

Return ONLY the JSON object, no other text."""

    return prompt


def call_llm_api(prompt: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
    """调用阿里百炼API"""
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant specialized in robotics and embodied AI."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 2000
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                
                # 解析JSON
                try:
                    # 清理可能的markdown代码块
                    content = content.strip()
                    if content.startswith('```json'):
                        content = content[7:]
                    if content.startswith('```'):
                        content = content[3:]
                    if content.endswith('```'):
                        content = content[:-3]
                    content = content.strip()
                    
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"  ⚠️ JSON解析失败: {e}")
                    print(f"  原始内容: {content[:200]}...")
                    return None
            else:
                print(f"  ⚠️ API错误 (attempt {attempt+1}): {response.status_code} - {response.text[:200]}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    
        except Exception as e:
            print(f"  ⚠️ 请求异常 (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    
    return None


def annotate_repository(repo_data: Dict[str, Any]) -> Optional[LLMAnnotation]:
    """对单个仓库进行LLM标注"""
    
    prompt = create_annotation_prompt(repo_data)
    result = call_llm_api(prompt)
    
    if not result:
        return None
    
    try:
        return LLMAnnotation(
            summary=result.get('summary', ''),
            relevance_score=result.get('relevance_score', 0),
            category=result.get('category', 'Unknown'),
            subcategory=result.get('subcategory', ''),
            robot_types=result.get('robot_types', []),
            tags=result.get('tags', []),
            capabilities=result.get('capabilities', []),
            mcp_tools=result.get('mcp_tools'),
            hardware_requirements=result.get('hardware_requirements', []),
            software_dependencies=result.get('software_dependencies', []),
            is_rosclaw_native=result.get('is_rosclaw_native', False),
            confidence=result.get('confidence', 0)
        )
    except Exception as e:
        print(f"  ⚠️ 解析标注结果失败: {e}")
        return None


def update_database(db_path: str, repo_id: int, annotation: LLMAnnotation):
    """更新数据库中的标注结果"""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE rosclaw_hub_resources SET
                llm_summary = ?,
                llm_relevance_score = ?,
                llm_category = ?,
                llm_key_features = ?,
                llm_analyzed_at = ?,
                llm_model = ?,
                domain_tags = ?,
                is_embodied = ?
            WHERE id = ?
        """, (
            annotation.summary,
            annotation.relevance_score,
            annotation.category,
            json.dumps({
                'subcategory': annotation.subcategory,
                'robot_types': annotation.robot_types,
                'tags': annotation.tags,
                'capabilities': annotation.capabilities,
                'mcp_tools': annotation.mcp_tools,
                'hardware_requirements': annotation.hardware_requirements,
                'software_dependencies': annotation.software_dependencies,
                'confidence': annotation.confidence
            }, ensure_ascii=False),
            datetime.now().isoformat(),
            MODEL,
            json.dumps(annotation.tags, ensure_ascii=False),
            annotation.is_rosclaw_native or annotation.relevance_score >= 70,
            repo_id
        ))
        
        conn.commit()
        
    except Exception as e:
        print(f"  ❌ 数据库更新失败: {e}")
        
    finally:
        conn.close()


def get_unannotated_repos(db_path: str, limit: int = 100) -> List[Dict]:
    """获取未标注或需要重新标注的仓库"""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 获取所有需要标注的记录（llm_analyzed_at为空，或旧标注的）
        cursor.execute("""
            SELECT id, type, repo_url, name, description, stars, source
            FROM rosclaw_hub_resources
            WHERE is_relevant = 1
            AND (llm_analyzed_at IS NULL 
                 OR llm_model IS NULL 
                 OR llm_model != ?)
            ORDER BY stars DESC
            LIMIT ?
        """, (MODEL, limit))
        
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        
        return [dict(zip(columns, row)) for row in rows]
        
    except Exception as e:
        print(f"  ❌ 查询失败: {e}")
        return []
        
    finally:
        conn.close()


def process_batch(db_path: str, repos: List[Dict], batch_num: int):
    """处理一批仓库"""
    
    print(f"\n🚀 批次 #{batch_num} | 处理 {len(repos)} 个仓库")
    print("=" * 60)
    
    success_count = 0
    fail_count = 0
    
    for i, repo in enumerate(repos, 1):
        print(f"\n[{i}/{len(repos)}] {repo['name']} ({repo['stars']}⭐)")
        print(f"  URL: {repo['repo_url'][:60]}...")
        
        # 调用LLM标注
        annotation = annotate_repository(repo)
        
        if annotation:
            update_database(db_path, repo['id'], annotation)
            print(f"  ✅ 标注成功 | 相关度: {annotation.relevance_score}/100 | 分类: {annotation.category}")
            print(f"  🏷️ 标签: {', '.join(annotation.tags[:5])}")
            if annotation.robot_types and annotation.robot_types != ['None']:
                print(f"  🤖 支持机器人: {', '.join(annotation.robot_types[:3])}")
            success_count += 1
        else:
            print(f"  ❌ 标注失败")
            fail_count += 1
        
        # 避免API限流
        time.sleep(0.5)
    
    print(f"\n📊 批次完成: ✅ {success_count} 成功, ❌ {fail_count} 失败")
    return success_count, fail_count


def run_annotation_pipeline(db_path: str = 'rosclaw_hub.db', total_limit: int = None):
    """运行完整标注流水线"""
    
    print("=" * 70)
    print("🤖 ROSClaw LLM Re-Annotation Pipeline")
    print("=" * 70)
    print(f"📁 数据库: {db_path}")
    print(f"🤖 模型: {MODEL}")
    print(f"🌐 API: 阿里百炼 Bailian")
    print(f"🎯 目标: 废弃旧标注，按ROSClaw生态重新评分")
    print("=" * 70)
    
    batch_num = 0
    total_success = 0
    total_fail = 0
    
    while True:
        batch_num += 1
        
        # 获取一批未标注的仓库
        repos = get_unannotated_repos(db_path, BATCH_SIZE)
        
        if not repos:
            print("\n✨ 所有仓库已标注完成！")
            break
        
        # 处理批次
        success, fail = process_batch(db_path, repos, batch_num)
        total_success += success
        total_fail += fail
        
        # 检查是否达到总数限制
        if total_limit and (total_success + total_fail) >= total_limit:
            print(f"\n⏹️ 已达到处理限制 ({total_limit})，暂停")
            break
        
        # 批次间休息
        print(f"\n⏳ 休息3秒后继续...")
        time.sleep(3)
    
    print("\n" + "=" * 70)
    print("📊 最终统计")
    print("=" * 70)
    print(f"  ✅ 成功标注: {total_success}")
    print(f"  ❌ 标注失败: {total_fail}")
    print(f"  📈 总计处理: {total_success + total_fail}")
    print("=" * 70)


if __name__ == '__main__':
    # 从命令行参数获取数据库路径
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'rosclaw_hub.db'
    
    # 可选: 限制处理数量用于测试
    test_limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    
    run_annotation_pipeline(db_path, test_limit)
