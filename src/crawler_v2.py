#!/usr/bin/env python3
"""
Rosclaw Crawler v2 - Strict Quality Crawler
Only collects:
1. Real MCP Servers (mcp-server, mcp-bridge, etc. with embodied AI relevance)
2. Real Agent Skills (skill.md, claude-skill, etc. for robotics/embodied AI)
3. Must be directly relevant to embodied intelligence, physical AI, robotics

Excludes:
- Pure algorithm/model repos (diffusion, RL, etc. without agent interface)
- Pure hardware projects without software agent interface
- Generated/template MCPs (ag2-mcp-servers mass-generated)
- IoT/cloud-only with no physical embodiment
- Tutorials, demos, lists, surveys
"""

import json
import re
import time
import urllib.request
import urllib.error
from urllib.parse import urlencode, urlparse
from datetime import datetime

# =============================================================================
# STRICT FILTER CONFIGURATION
# =============================================================================

# --- Hard Exclusion Patterns (auto-remove) ---
HARD_EXCLUDE_PATTERNS = [
    r'awesome-',
    r'paper-list',
    r'survey',
    r'generated\s+by\s+mcp\.ag2\.ai',
    r'tutorial',
    r'demo(?!n)',
    r'example',
    r'sample-',
    r'youtube',
    r'video',
    r'discord',
    r'smart\s+home(?!\s+robot)',
    r'heat\s+pump',
    r'motor\s+vehicle\s+department',
    r'ledger\s+hardware\s+wallet',
    r'b2b',
    r'exploring',
    r'webcam',
    r'camera-mcp(?!.*robot)',
    r'camera\s+mcp(?!.*robot)',
]

# --- True MCP Evidence (name patterns) ---
TRUE_MCP_PATTERNS = [
    r'mcp[-_]?server',
    r'mcp[-_]?bridge',
    r'ros[-_]?mcp',
    r'claude[-_]?mcp',
    r'[-_]?mcp[-_]?',
]

# --- True Skill Evidence (name patterns) ---
TRUE_SKILL_PATTERNS = [
    r'skill\.md',
    r'claude[-_]?skill',
    r'\.claude',
    r'agent[-_]?skill',
    r'[-_]?skill[-_]?',
]

# --- MCP Description Evidence ---
MCP_DESCRIPTION_EVIDENCE = [
    'mcp server', 'model context protocol', 'connect ai', 'llm agent',
    'claude desktop', 'anthropic', 'agent tool', 'ai assistant',
]

# --- Weak keywords that alone don't justify keeping ---
WEAK_EMBODIED_KEYWORDS = [
    'iot', 'device', 'hardware', 'sensor', 'actuator', 'physical',
    'industrial', 'manufacturing', 'camera', 'serial', 'ble', 'bluetooth',
]

# --- Strong embodied keywords (must have at least one for loose MCPs) ---
STRONG_EMBODIED_KEYWORDS = [
    'robot', 'robotic', 'robotics', 'drone', 'uav', 'quadcopter',
    'ros', 'ros2', 'gazebo', 'mujoco', 'isaac', 'isaaclab',
    '3d printer', '3d-printer', 'bambu', 'klipper', 'prusa', 'cnc',
    'plc', 'modbus', 'arduino', 'esp32', 'stm32',
    'servo', 'motor', 'gripper', 'manipulator', 'arm', 'legged',
    'slam', 'navigation', 'autonomous', 'locomotion',
    'humanoid', 'quadruped', 'biped', 'mobile robot',
    'mavlink', 'px4', 'ardupilot', 'flight controller',
    'pick and place', 'warehouse', 'agv', 'amr',
    'kinematics', 'dynamics', 'trajectory', 'motion planning',
    'sim2real', 'digital twin',
]

# --- Strong Embodied Indicators ---
STRONG_EMBODIED_INDICATORS = [
    '3d printer', 'bambu', 'klipper', 'drone', 'mavlink', 'px4', 'ardupilot',
    'robot', 'robotic', 'robotics', 'manipulator', 'gripper', 'arm',
    'ros', 'ros2', 'gazebo', 'mujoco', 'isaac sim', 'isaaclab', 'nvidia isaac',
    'plc', 'modbus', 'arduino', 'esp32', 'stm32', 'microcontroller',
    'slam', 'navigation', 'autonomous', 'self-driving', 'locomotion',
    'servo', 'motor', 'actuator', 'sensor', 'lidar', 'imu', 'encoder',
    'kinematics', 'dynamics', 'trajectory', 'motion planning',
    'gr00t', 'open pi zero', 'pi0', 'diffusion policy', 'behavior cloning',
    'sim2real', 'simulation', 'digital twin', 'physics engine',
    'humanoid', 'quadruped', 'biped', 'legged', 'mobile robot',
    'cnc', 'gcode', 'machining', 'manufacturing', 'fabrication',
    'agv', 'amr', 'warehouse robot', 'pick and place',
]

# --- Simulation Platforms (keep if true MCP/skill) ---
SIMULATION_PLATFORMS = [
    'habitat-sim', 'isaaclab', 'gymnasium', 'genesis',
]

# --- Pure Algorithm Libraries (exclude unless true MCP/skill) ---
PURE_ALGO_LIBS = [
    'stable-baselines', 'cleanrl', 'rllib', 'sb3',
    'roboticsdiffusiontransformer', 'diffusion policy',
    'open-pi-zero', 'pi0', 'gr00t', 'gr1', 'gr2',
    'octo', 'act', 'aloha', 'openvla', 'rt-x', 'rt-1', 'rt-2',
    'navrl', 'asap', 'psi0', 'vla', 'vln',
    '3d-diffuser', 'robodiff', 'diffusion',
]

# --- Pure Hardware (exclude unless has clear agent interface) ---
PURE_HARDWARE = [
    'openarm', 'dummy-robot', 'spotmicro', 'low_cost_robot',
    'poppy-project', 'inmoov', 'reachy', 'stretch',
]

# --- Trusted Publishers ---
TRUSTED_PUBLISHERS = [
    'ros-claw', 'dbwls99706',
]

# =============================================================================
# FILTER FUNCTIONS
# =============================================================================

def check_hard_exclude(name: str, desc: str) -> tuple[bool, str]:
    """Check if item matches hard exclusion patterns."""
    text = f"{name} {desc}".lower()
    for pattern in HARD_EXCLUDE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True, f"Hard exclude: matches {pattern}"
    return False, ""


def is_true_mcp(name: str, desc: str) -> tuple[bool, str]:
    """Check if this is a genuine MCP server with embodied intelligence relevance."""
    name_lower = name.lower()
    desc_lower = desc.lower()

    # Name-based evidence
    for pattern in TRUE_MCP_PATTERNS:
        if re.search(pattern, name_lower):
            # Check if it's actually about embodied intelligence
            for indicator in STRONG_EMBODIED_INDICATORS:
                if indicator in name_lower or indicator in desc_lower:
                    return True, f"True MCP with embodied indicator: {indicator}"
            # If name has mcp but no embodied indicator, still accept if description has MCP evidence
            # BUT must also have at least one STRONG embodied keyword
            has_mcp_evidence = any(evidence in desc_lower for evidence in MCP_DESCRIPTION_EVIDENCE)
            has_strong_embodied = any(kw in desc_lower for kw in STRONG_EMBODIED_KEYWORDS)
            if has_mcp_evidence and has_strong_embodied:
                return True, f"True MCP with description evidence + strong embodied keyword"
            # Reject weak-only MCPs
            return False, "MCP name but no strong embodied/physical relevance"

    # Description-based evidence
    for evidence in MCP_DESCRIPTION_EVIDENCE:
        if evidence in desc_lower:
            # Must also have embodied indicator
            for indicator in STRONG_EMBODIED_INDICATORS:
                if indicator in desc_lower:
                    return True, f"MCP evidence + embodied indicator: {indicator}"
            return False, "MCP description evidence but no embodied relevance"

    return False, "Not a recognized MCP Server"


def is_true_skill(name: str, desc: str) -> tuple[bool, str]:
    """Check if this is a genuine Agent Skill with embodied intelligence relevance."""
    name_lower = name.lower()
    desc_lower = desc.lower()

    for pattern in TRUE_SKILL_PATTERNS:
        if re.search(pattern, name_lower):
            # Must have embodied intelligence indicator
            for indicator in STRONG_EMBODIED_INDICATORS:
                if indicator in name_lower or indicator in desc_lower:
                    return True, f"True Skill with embodied indicator: {indicator}"
            # Check strong embodied keywords
            for kw in STRONG_EMBODIED_KEYWORDS:
                if kw in name_lower or kw in desc_lower:
                    return True, f"True Skill with embodied keyword: {kw}"
            # No embodied relevance = reject
            return False, "Agent Skill form but no embodied/robotics relevance"

    # Special: ROS 2 engineering skills
    if 'ros' in name_lower and 'engineer' in desc_lower:
        return True, "ROS engineering skill"
    if 'ros2' in name_lower and ('skill' in desc_lower or 'agent' in desc_lower):
        return True, "ROS2 agent skill"

    return False, "Not a recognized Agent Skill"


def has_embodied_relevance(name: str, desc: str) -> tuple[bool, int]:
    """Check embodied intelligence relevance. Returns (has_relevance, score)."""
    text = f"{name} {desc}".lower()
    score = 0
    matched = []

    for indicator in STRONG_EMBODIED_INDICATORS:
        # Use word boundary for short keywords to avoid partial matches
        if len(indicator) <= 4:
            pattern = r'\b' + re.escape(indicator) + r'\b'
            if re.search(pattern, text):
                score += 1
                matched.append(indicator)
        else:
            if indicator in text:
                score += 1
                matched.append(indicator)

    # Extra points for strong signals
    if re.search(r'\bros\b|\bros2\b', text):
        score += 2
    if 'robot' in text:
        score += 2
    if 'mujoco' in text or 'isaac' in text:
        score += 1
    if 'sim2real' in text or 'simulation' in text:
        score += 1

    return score >= 2, score


def is_pure_algorithm(name: str) -> tuple[bool, str]:
    """Check if this is a pure algorithm/model repo without agent interface.
    Only checks the repo name (after /), not the owner name."""
    # Extract just the repo name, not owner
    repo_name = name.split('/')[-1].lower() if '/' in name else name.lower()
    for algo in PURE_ALGO_LIBS:
        # Use word boundary matching to avoid partial matches
        if re.search(r'\b' + re.escape(algo) + r'\b', repo_name):
            return True, f"Pure algorithm/model without MCP/Skill interface: {algo}"
    return False, ""


def is_pure_hardware(name: str) -> tuple[bool, str]:
    """Check if this is pure hardware without software agent interface.
    Only checks the repo name (after /), not the owner name.
    If repo name contains 'mcp' or 'skill', it's not pure hardware."""
    repo_name = name.split('/')[-1].lower() if '/' in name else name.lower()
    # If it has MCP or Skill in the name, it's not pure hardware
    if 'mcp' in repo_name or 'skill' in repo_name:
        return False, ""
    for hw in PURE_HARDWARE:
        if re.search(r'\b' + re.escape(hw) + r'\b', repo_name):
            return True, f"Pure hardware project without MCP/Skill interface: {hw}"
    return False, ""


def is_trusted_publisher(name: str) -> bool:
    """Check if from a trusted publisher."""
    name_lower = name.lower()
    for pub in TRUSTED_PUBLISHERS:
        if pub in name_lower:
            return True
    return False


def strict_classify(name: str, description: str, url: str = "") -> tuple[str, str, float]:
    """
    Strict classification for crawler v2.
    Returns: (decision, reason, confidence)
    decision: 'keep', 'remove', 'review'
    """
    desc = description or ""

    # 1. Trusted publishers bypass all checks
    if is_trusted_publisher(name):
        return 'keep', 'Trusted publisher', 1.0

    # 2. Hard exclusions
    is_excluded, exclude_reason = check_hard_exclude(name, desc)
    if is_excluded:
        return 'remove', exclude_reason, 0.95

    # 3. Check if pure algorithm
    is_algo, algo_reason = is_pure_algorithm(name)
    if is_algo:
        return 'remove', algo_reason, 0.9

    # 4. Check if pure hardware
    is_hw, hw_reason = is_pure_hardware(name)
    if is_hw:
        return 'remove', hw_reason, 0.9

    # 5. Check if true MCP
    is_mcp, mcp_reason = is_true_mcp(name, desc)
    if is_mcp:
        return 'keep', mcp_reason, 0.85

    # 6. Check if true Skill
    is_skill, skill_reason = is_true_skill(name, desc)
    if is_skill:
        return 'keep', skill_reason, 0.85

    # 7. Has embodied relevance but not MCP/Skill form
    has_relevance, score = has_embodied_relevance(name, desc)
    if has_relevance:
        return 'remove', f"Has embodied relevance (score={score}) but not a recognized MCP Server or Agent Skill", 0.7

    # 8. No relevance at all
    return 'remove', "No embodied intelligence relevance and not a recognized MCP/Skill", 0.8


# =============================================================================
# GITHUB API SEARCH
# =============================================================================

GITHUB_SEARCH_QUERIES = [
    # MCP Servers for robotics
    'mcp-server robotics',
    'mcp-server robot',
    'mcp-server ros',
    'mcp-server ros2',
    'mcp-server drone',
    'mcp-server 3d-printer',
    'mcp-server mujoco',
    'mcp-server isaac',
    'mcp-server gazebo',
    'mcp-server slam',
    'mcp-server navigation',
    'mcp-server manipulator',
    'mcp-server servo',
    'mcp-server actuator',
    'mcp-server plc',
    'mcp-server modbus',
    'mcp-server arduino',
    'mcp-server esp32',
    'mcp-server cnc',
    'mcp-server manufacturing',
    # Agent Skills for robotics
    'skill.md robotics',
    'skill.md robot',
    'skill.md ros',
    'claude-skill robot',
    'agent-skill robotics',
    'claude skill manipulator',
    # Specific platforms
    'mcp-server isaaclab',
    'mcp-server genesis',
    'mcp-server habitat',
]


def github_search(query: str, token: str = None, per_page: int = 30) -> list[dict]:
    """Search GitHub repositories."""
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'rosclaw-crawler-v2',
    }
    if token:
        headers['Authorization'] = f'token {token}'

    url = f'https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=updated&order=desc&per_page={per_page}'

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            return data.get('items', [])
    except urllib.error.HTTPError as e:
        print(f"GitHub API error: {e.code} - {e.reason}")
        return []
    except Exception as e:
        print(f"Error: {e}")
        return []


def fetch_repo_details(owner: str, repo: str, token: str = None) -> dict:
    """Fetch detailed repo info including README."""
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'rosclaw-crawler-v2',
    }
    if token:
        headers['Authorization'] = f'token {token}'

    # Basic repo info
    url = f'https://api.github.com/repos/{owner}/{repo}'
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            repo_data = json.loads(resp.read().decode())
    except Exception as e:
        return {}

    # README content
    readme_url = f'https://api.github.com/repos/{owner}/{repo}/readme'
    req = urllib.request.Request(readme_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            readme_data = json.loads(resp.read().decode())
            import base64
            readme_content = base64.b64decode(readme_data.get('content', '')).decode('utf-8', errors='ignore')[:5000]
            repo_data['readme_content'] = readme_content
    except Exception:
        repo_data['readme_content'] = ''

    return repo_data


# =============================================================================
# CRAWLER MAIN
# =============================================================================

def run_crawler(github_token: str = None, max_results_per_query: int = 10) -> dict:
    """
    Run the strict crawler.
    Returns dict with 'keep' and 'remove' lists.
    """
    results = {
        'timestamp': datetime.now().isoformat(),
        'keep': [],
        'remove': [],
        'stats': {
            'queries_run': 0,
            'repos_found': 0,
            'kept': 0,
            'removed': 0,
        }
    }

    seen = set()

    for query in GITHUB_SEARCH_QUERIES:
        print(f"\n[Query] {query}")
        repos = github_search(query, token=github_token, per_page=max_results_per_query)
        results['stats']['queries_run'] += 1

        for repo in repos:
            repo_id = repo.get('full_name', '')
            if repo_id in seen:
                continue
            seen.add(repo_id)
            results['stats']['repos_found'] += 1

            name = repo.get('full_name', '')
            description = repo.get('description') or ''
            url = repo.get('html_url', '')

            decision, reason, confidence = strict_classify(name, description, url)

            item = {
                'name': name,
                'description': description,
                'url': url,
                'stars': repo.get('stargazers_count', 0),
                'language': repo.get('language', ''),
                'updated_at': repo.get('updated_at', ''),
                'decision': decision,
                'reason': reason,
                'confidence': confidence,
            }

            if decision == 'keep':
                results['keep'].append(item)
                results['stats']['kept'] += 1
                print(f"  ✅ KEEP: {name} ({reason})")
            else:
                results['remove'].append(item)
                results['stats']['removed'] += 1
                print(f"  ❌ REMOVE: {name} ({reason})")

        # Rate limit protection
        time.sleep(2)

    return results


def save_results(results: dict, output_path: str = None):
    """Save crawler results to JSON."""
    if not output_path:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = f'crawler_v2_results_{timestamp}.json'

    with open(output_path, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"Results saved to: {output_path}")
    print(f"Stats: {results['stats']}")
    print(f"Kept: {len(results['keep'])} | Removed: {len(results['remove'])}")
    return output_path


# =============================================================================
# CLI
# =============================================================================

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Rosclaw Crawler v2 - Strict Quality Filter')
    parser.add_argument('--github-token', help='GitHub personal access token')
    parser.add_argument('--max-per-query', type=int, default=10, help='Max results per query')
    parser.add_argument('--output', help='Output JSON file path')
    parser.add_argument('--test-filter', help='Test filter on a repo name (format: owner/repo)')
    args = parser.parse_args()

    if args.test_filter:
        name = args.test_filter
        desc = input(f"Description for {name}: ") or ""
        d, r, c = strict_classify(name, desc)
        print(f"\nResult: {d}")
        print(f"Reason: {r}")
        print(f"Confidence: {c}")
        exit(0)

    print("="*60)
    print("Rosclaw Crawler v2 - Strict Quality Filter")
    print("="*60)

    results = run_crawler(
        github_token=args.github_token,
        max_results_per_query=args.max_per_query,
    )
    save_results(results, args.output)
