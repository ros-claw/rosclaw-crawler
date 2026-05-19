#!/usr/bin/env python3
"""
LLM Judge - Use DeepSeek API to evaluate if a repo is truly relevant to embodied AI/robotics.
"""

import json
import urllib.request
import urllib.error
from typing import Optional

DEEPSEEK_API_KEY = "DEEPSEEK_KEY_PLACEHOLDER"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-pro"

SYSTEM_PROMPT = """You are an expert judge evaluating GitHub repositories for relevance to embodied intelligence, physical AI, and robotics.

A repository is RELEVANT only if it meets ALL of these criteria:
1. It is a real MCP Server or Agent Skill (has actual MCP/skill implementation, not just a concept)
2. It is directly related to embodied intelligence, physical AI, robotics, or hardware automation
3. It can be directly used by an AI agent to interact with physical systems

NOT relevant:
- Pure software tools with no physical/hardware connection
- Collections/lists of skills without actual implementation
- Frameworks/libraries without MCP/Skill interface
- Tutorials, demos, examples
- General AI/ML without physical embodiment

Respond ONLY in JSON format:
{
  "relevant": true/false,
  "confidence": 0-100,
  "category": "robotics|drone|3d_printing|ros|industrial|simulation|sensor|actuator|other",
  "reason": "brief explanation"
}
"""


def judge_repo(name: str, description: str, readme: str, url: str) -> dict:
    """Ask DeepSeek to judge a repository."""
    user_prompt = f"""Repository: {name}
URL: {url}
Description: {description}

README (first 2000 chars):
{readme[:2000]}

Evaluate this repository. Is it truly relevant to embodied intelligence/physical AI/robotics as an MCP Server or Agent Skill?"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }

    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 500,
        "response_format": {"type": "json_object"},
    }

    req = urllib.request.Request(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        data=json.dumps(data).encode(),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            content = result["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as e:
        return {
            "relevant": False,
            "confidence": 0,
            "category": "error",
            "reason": f"LLM API error: {str(e)}",
        }


def batch_judge(items: list[dict], delay: float = 1.0) -> list[dict]:
    """Judge multiple repos with rate limiting."""
    import time

    results = []
    for i, item in enumerate(items):
        print(f"[{i+1}/{len(items)}] Judging {item['name']}...")
        result = judge_repo(
            item["name"],
            item.get("description", ""),
            item.get("readme", ""),
            item.get("url", ""),
        )
        results.append({
            "name": item["name"],
            "llm_result": result,
            "raw_data": item,
        })
        time.sleep(delay)

    return results


if __name__ == "__main__":
    # Test
    test = judge_repo(
        "dbwls99706/ros2-engineering-skills",
        "Agent skill for production-grade ROS 2 development",
        "# ros2-engineering-skills\nAgent skill for production-grade ROS 2 development",
        "https://github.com/dbwls99706/ros2-engineering-skills",
    )
    print(json.dumps(test, indent=2))
