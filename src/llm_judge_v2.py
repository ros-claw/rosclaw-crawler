#!/usr/bin/env python3
"""
LLM Judge v2 - Improved prompt for better accuracy in evaluating robotics/embodied AI repos
"""

import json
import urllib.request
import os
from typing import Dict

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-pro"

def llm_judge_v2(name: str, desc: str, readme: str) -> Dict:
    """
    Improved LLM judge with better prompt engineering
    Returns: {"relevant": bool, "confidence": int, "reason": str, "category": str}
    """
    
    prompt = f"""You are an expert curator for embodied AI and robotics tools. Evaluate if this GitHub repository is a genuine MCP Server or Agent Skill that is directly relevant to physical AI, robotics, or embodied intelligence.

Repository: {name}
Description: {desc}
README excerpt: {readme[:2000]}

EVALUATION CRITERIA:
1. MUST be an MCP Server (has mcp-server in name or implements MCP protocol) OR an Agent Skill (has SKILL.md or skill in name)
2. MUST be directly relevant to: robotics, physical AI, embodied intelligence, robot simulation, robot control, drone, autonomous vehicle, industrial automation, or humanoid robots
3. MUST be callable/usable by an AI agent (not just a library or framework)
4. Exclude: pure software tools, web scrapers, general APIs, unrelated IoT devices

CATEGORIES (if relevant):
- robotics: General robotics tools
- humanoid: Humanoid robots (Optimus, Atlas, Digit, etc.)
- manipulation: Robot arm manipulation, grasping
- navigation: SLAM, path planning, autonomous navigation
- simulation: Physics simulators (MuJoCo, Gazebo, Isaac Sim, etc.)
- drone: UAV, drone control
- industrial: Factory automation, cobots, PLC
- control: MPC, optimal control, reinforcement learning for control
- vision: Robot perception, computer vision for robotics

Reply ONLY with JSON:
{{"relevant":true/false,"confidence":0-100,"reason":"One sentence explaining why","category":"category_name"}}"""

    req = urllib.request.Request(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        data=json.dumps({
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.05,
            "max_tokens": 150,
            "response_format": {"type": "json_object"},
        }).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
        },
        method="POST",
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = json.loads(resp.read().decode())["choices"][0]["message"]["content"]
            result = json.loads(content)
            
            # Validate and normalize
            if "relevant" not in result:
                result["relevant"] = False
            if "confidence" not in result:
                result["confidence"] = 0
            if "reason" not in result:
                result["reason"] = "No reason provided"
            if "category" not in result:
                result["category"] = "general"
                
            return result
            
    except Exception as e:
        return {
            "relevant": False,
            "confidence": 0,
            "reason": f"Error: {str(e)[:100]}",
            "category": "error"
        }

if __name__ == '__main__':
    # Test
    result = llm_judge_v2(
        "test/ros2-mcp-server",
        "MCP server for ROS2",
        "# ROS2 MCP Server\n\nThis is an MCP server for ROS2 robots."
    )
    print(json.dumps(result, indent=2))
