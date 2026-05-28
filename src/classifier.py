#!/usr/bin/env python3
"""
Robust Classifier for MCP vs Skill vs Neither
Fixes previous misclassification issues
"""

import re
from typing import Dict, Tuple, Optional


def classify_repo(name: str, description: str = "", readme_content: str = "") -> Tuple[str, int, str]:
    """
    Classify a repository as 'mcp', 'skill', or 'neither'
    
    Returns:
        (item_type, confidence, reason)
    """
    name_lower = name.lower()
    desc_lower = (description or "").lower()
    readme_lower = (readme_content or "").lower()
    combined = f"{name_lower} {desc_lower} {readme_lower}"
    
    # ===== STEP 1: Check for SKILL indicators (highest priority) =====
    
    # Initialize skill scoring
    skill_score = 0
    skill_reasons = []
    
    # Check for skill in the repo name part (after /)
    repo_part = name_lower.split('/')[-1] if '/' in name_lower else name_lower
    
    skill_keywords = ['skill', 'skills', 'agent-skill', 'claude-skill']
    for kw in skill_keywords:
        if kw in repo_part:
            skill_score += 2
            skill_reasons.append(f"Repo name contains '{kw}'")
    
    # Check for specific skill patterns
    if 'skill' in repo_part and ('robot' in combined or 'ros' in combined):
        skill_score += 2
        skill_reasons.append("Skill + robotics keywords")
    
    skill_indicators = [
        r'-skill$',           # Ends with -skill
        r'-skills$',          # Ends with -skills
        r'\.skill$',          # Ends with .skill
        r'\.skills$',         # Ends with .skills
    ]
    
    for pattern in skill_indicators:
        if re.search(pattern, name_lower):
            skill_score += 3
            skill_reasons.append(f"Name matches skill pattern: {pattern}")
    
    # Check README for SKILL.md
    if 'skill.md' in readme_lower or 'skills.md' in readme_lower:
        skill_score += 3
        skill_reasons.append("Has SKILL.md in repo")
    
    # Check for skill-specific content
    if 'claude code skill' in readme_lower or 'claude-code skill' in readme_lower:
        skill_score += 2
        skill_reasons.append("Claude Code skill mentioned")
    
    if skill_score >= 3:
        # It's a skill, now check if it's robotics-related
        is_robotics = _is_robotics_related(combined)
        if is_robotics:
            return ('skill', min(95, 70 + skill_score * 3), 
                    f"Skill detected ({', '.join(skill_reasons[:2])})")
        else:
            return ('neither', 30, "Skill but not robotics-related")
    
    # ===== STEP 2: Check for MCP indicators =====
    mcp_score = 0
    mcp_reasons = []
    
    # Check for MCP in repo name (case insensitive)
    mcp_keywords = ['mcp']
    for kw in mcp_keywords:
        if kw in repo_part:
            mcp_score += 3  # Increased from 2 to 3
            mcp_reasons.append(f"Repo name contains '{kw}'")
    
    mcp_indicators = [
        r'-mcp$',             # Ends with -mcp
        r'-mcp-server$',      # Ends with -mcp-server
        r'-mcp-client$',      # Ends with -mcp-client
        r'/mcp-',             # Starts with mcp- after owner
        r'mcp[_-]server',     # mcp_server or mcp-server
        r'mcp[_-]client',     # mcp_client or mcp-client
    ]
    
    for pattern in mcp_indicators:
        if re.search(pattern, name_lower):
            mcp_score += 3
            mcp_reasons.append(f"Name matches MCP pattern: {pattern}")
    
    for pattern in mcp_indicators:
        if re.search(pattern, name_lower):
            mcp_score += 3
            mcp_reasons.append(f"Name matches MCP pattern: {pattern}")
    
    # Check README for MCP protocol
    mcp_protocol_indicators = [
        'model context protocol',
        'mcp server',
        'mcp-server',
        'mcp client',
        'mcp-client',
        'stdio transport',
        'sse transport',
        '@modelcontextprotocol',
    ]
    
    for indicator in mcp_protocol_indicators:
        if indicator in readme_lower:
            mcp_score += 2
            mcp_reasons.append(f"README mentions: {indicator}")
    
    if mcp_score >= 3:
        # It's an MCP, now check if it's robotics-related
        is_robotics = _is_robotics_related(combined)
        if is_robotics:
            return ('mcp', min(95, 70 + mcp_score * 3),
                    f"MCP detected ({', '.join(mcp_reasons[:2])})")
        else:
            return ('neither', 30, "MCP but not robotics-related")
    
    # ===== STEP 3: Neither MCP nor Skill =====
    return ('neither', 20, "No MCP or Skill indicators found")


def _is_robotics_related(text: str) -> bool:
    """Check if text is related to robotics/embodied AI"""
    
    # Strong robotics keywords (must have at least one)
    strong_keywords = [
        'robot', 'robotics', 'ros', 'ros2', 'mujoco', 'gazebo', 'isaac',
        'drone', 'uav', 'mavlink', 'px4', 'ardupilot', 'turtlebot',
        'kinova', 'franka', 'ur5', 'ur10', 'unitree', 'boston dynamics',
        'spot robot', 'go2 robot', 'g1 humanoid', 'humanoid',
        'manipulator', 'gripper', 'grasping', 'slam', 'navigation',
        'lidar', 'realsense', 'servo', 'actuator', 'encoder',
        'plc', 'modbus', 'arduino', 'esp32', 'jetson',
        '3d printer', '3d printing', 'bambu', 'prusa', 'klipper', 'cnc',
        'mechanical', 'automation', 'kinematics', 'dynamics',
        'reachy', 'pepper', 'nao', 'vector', 'anki',
        'openai robotics', 'physical ai', 'embodied',
    ]
    
    # Exclusion keywords (if these dominate, it's not robotics)
    exclusion_keywords = [
        'microsoft dynamics', 'd365', 'business central',
        'excel', 'powerpoint', 'word', 'office 365',
        'pure software', 'web app', 'mobile app',
        'game', 'gaming', 'entertainment',
        'social media', 'chat', 'messaging',
    ]
    
    has_strong = any(kw in text for kw in strong_keywords)
    has_exclusion = any(kw in text for kw in exclusion_keywords)
    
    # Must have strong keyword and not be dominated by exclusion
    return has_strong and not has_exclusion


def verify_not_empty(name: str, readme_content: str = "", stars: int = 0) -> Tuple[bool, str]:
    """
    Verify repository is not empty or nearly empty
    
    Returns:
        (is_valid, reason)
    """
    readme_lower = (readme_content or "").lower()
    
    # Check for empty indicators
    if stars == 0 and len(readme_content) < 200:
        return (False, "Empty or nearly empty repository")
    
    if len(readme_content) < 100:
        return (False, "README too short (< 100 chars)")
    
    # Check for placeholder content
    placeholder_indicators = [
        'todo',
        'work in progress',
        'wip',
        'coming soon',
        'placeholder',
        'initial commit',
    ]
    
    placeholder_count = sum(1 for indicator in placeholder_indicators 
                           if indicator in readme_lower)
    
    if placeholder_count >= 2 and len(readme_content) < 500:
        return (False, "Placeholder/WIP content only")
    
    return (True, "Repository has meaningful content")


def full_evaluate(name: str, description: str = "", readme_content: str = "", stars: int = 0) -> Dict:
    """
    Full evaluation: classify + verify + robotics check
    
    Returns dict with:
        - item_type: 'mcp' | 'skill' | 'neither'
        - decision: 'keep' | 'remove'
        - confidence: 0-100
        - reason: explanation
        - site_status: 'pending' | 'removed'
    """
    
    # Step 1: Check if empty
    is_valid, empty_reason = verify_not_empty(name, readme_content, stars)
    if not is_valid:
        return {
            'item_type': 'neither',
            'decision': 'remove',
            'confidence': 95,
            'reason': f"Empty repo: {empty_reason}",
            'site_status': 'removed'
        }
    
    # Step 2: Classify
    item_type, confidence, classify_reason = classify_repo(name, description, readme_content)
    
    if item_type == 'neither':
        return {
            'item_type': 'neither',
            'decision': 'remove',
            'confidence': confidence,
            'reason': classify_reason,
            'site_status': 'removed'
        }
    
    # Step 3: It's a valid MCP or Skill
    return {
        'item_type': item_type,
        'decision': 'keep',
        'confidence': confidence,
        'reason': classify_reason,
        'site_status': 'pending'
    }


# Test cases
if __name__ == '__main__':
    test_cases = [
        # (name, description, expected_type)
        ("jherrodthomas/robotics-skills-suite", "Robotics skills", "skill"),
        ("arpitg1304/robotics-agent-skills", "Agent skills", "skill"),
        ("adityakamath/ros2-skill", "ROS2 skill", "skill"),
        ("dbwls99706/ros2-engineering-skills", "Engineering skills", "skill"),
        ("DMontgomery40/mcp-3D-printer-server", "3D printer MCP", "mcp"),
        ("dynamics365ninja/d365fo-mcp-server", "Dynamics 365", "neither"),
        ("opentiny/tiny-robot", "Tiny robot", "neither"),
        ("darshan-kt/turtle_mcp_ros2", "Turtle", "mcp"),  # Would fail empty check
        ("robotmcp/ros-mcp-server", "ROS MCP", "mcp"),
    ]
    
    print("Testing classifier:")
    print("="*70)
    
    for name, desc, expected in test_cases:
        result = classify_repo(name, desc)
        status = "✅" if result[0] == expected else "❌"
        print(f"{status} {name}")
        print(f"   Expected: {expected}, Got: {result[0]} (confidence: {result[1]}%)")
        print(f"   Reason: {result[2]}")
        print()
