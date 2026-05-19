"""ROSClaw Ecology Crawler - Configuration & Keyword Matrix"""

import os

# API Tokens
GITHUB_TOKEN = os.getenv(
    "GITHUB_TOKEN",
    "os.getenv("GITHUB_TOKEN", "")",
)
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
GOOGLE_CLOUD_API_KEY = os.getenv(
    "GOOGLE_CLOUD_API_KEY",
    "AIzaSyCX_EhVhxG6BiVQ1yZ6Fa6SkNrAYBuJidE",
)

# LLM Configuration (OpenAI-compatible API)
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://api.kimi.com/coding/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "kimi")
LLM_BATCH_SIZE = int(os.getenv("LLM_BATCH_SIZE", "3"))


# Proxy for curl_cffi
CURL_PROXIES = {
    "https": "socks5h://127.0.0.1:1080",
    "http": "socks5h://127.0.0.1:1080",
}

# Database
DB_PATH = os.getenv("ROSCLAW_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "rosclaw_hub.db"))

# Embodied AI / Physical AI Keywords Matrix (English + Chinese)
KEYWORDS_MATRIX = {
    "core_embodied": [
        "Embodied AI", "具身智能",
        "Physical AI", "物理AI",
        "Robotics", "机器人学",
        "Human-Robot Interaction", "人机交互", "HRI",
        "Bipedal", "Quadruped", "双足", "四足",
        "Dexterous Hand", "Manipulator", "Robotic Arm", "灵巧手", "机械臂",
        "Teleoperation", "遥操作",
    ],
    "models_paradigms": [
        "Vision-Language-Action", "VLA", "视觉语言动作模型",
        "Vision-Language Navigation", "VLN", "视觉语言导航",
        "World Models", "世界模型",
        "LLM Robot Control", "大语言模型控制",
        "Foundation Models for Robotics", "机器人基础模型",
    ],
    "perception_spatial": [
        "Spatial Intelligence", "空间智能",
        "SLAM", "Simultaneous Localization and Mapping", "即时定位与建图",
        "3D Reconstruction", "3D重建",
        "NeRF", "3D Gaussian Splatting", "3DGS",
        "Computer Vision", "计算机视觉",
        "Sensor Fusion", "传感器融合",
        "Depth Estimation", "Pose Estimation", "深度估计", "位姿估计",
    ],
    "simulation_control": [
        "Sim-to-Real", "仿真到现实",
        "Reinforcement Learning", "强化学习", "RL",
        "Imitation Learning", "Action Chunking", "ACT", "模仿学习",
        "Physics Engine", "物理引擎",
        "MuJoCo", "mjlab", "Newton-physics", "Isaac Sim", "Gazebo", "PyBullet",
        "ROS", "ROS 2", "DDS",
        "Kinematics", "Dynamics", "WBC", "MPC", "运动学", "动力学",
    ],
    "industry_hardware": [
        "Industrial Automation", "工业自动化",
        "IoT", "Internet of Things", "智能硬件", "物联网",
        "Embedded Systems", "Jetson", "Raspberry Pi", "嵌入式",
    ],
}

# Flattened keyword list for quick matching
ALL_EMBODIED_KEYWORDS = []
for cat, words in KEYWORDS_MATRIX.items():
    ALL_EMBODIED_KEYWORDS.extend(words)

# Additional skill-specific keywords (non-embodied but useful for skill discovery)
SKILL_KEYWORDS = [
    "agent skill", "openclaw skill", "claude skill", "ai skill",
    "coding skill", "developer skill", "programming skill",
    "LangChain skill", "CrewAI skill", "AutoGen skill", "LlamaIndex skill",
    "cursor skill", "copilot skill", "vscode skill",
    "writing skill", "research skill", "analysis skill",
    "chatgpt skill", "gpt skill", "llm skill",
    "tool skill", "plugin skill", "extension skill",
]

# --- GitHub Search Queries ---

def _build_queries():
    queries = []
    embodied_terms = [
        "Robotics", "Embodied AI", "Physical AI",
        "Manipulator", "VLA", "World Models",
        "Isaac Sim", "mjlab", "ROS 2", "SLAM",
        "IoT", "Spatial Intelligence", "Sim-to-Real",
        "Computer Vision", "Sensor Fusion", "Reinforcement Learning",
        "MuJoCo", "Gazebo", "PyBullet", "Teleoperation",
        "Dexterous Hand", "Bipedal", "Quadruped",
        "Industrial Automation", "Embedded Systems",
        "LLM Robot Control", "Foundation Models for Robotics",
    ]

    # MCP + Embodied
    for term in embodied_terms:
        queries.append(f'"MCP" AND "{term}"')
        queries.append(f'"Model Context Protocol" AND "{term}"')

    # Agent Skill + Embodied
    for term in embodied_terms[:12]:
        queries.append(f'"Agent Skill" AND "{term}"')
        queries.append(f'"agent skill" AND "{term}"')

    # MCP + general skill keywords
    for kw in SKILL_KEYWORDS[:15]:
        queries.append(f'"MCP" AND "{kw}"')

    # Skill + general tech (broad net for agent skills)
    for kw in SKILL_KEYWORDS:
        queries.append(f'"{kw}"')

    # Direct embodied repo searches (no MCP/Skill constraint)
    for term in ["Embodied AI", "Physical AI", "Robotics", "ROS 2", "SLAM", "VLA", "Sim-to-Real", "Isaac Sim", "MuJoCo"]:
        queries.append(f'"{term}" in:readme')

    # Specific ecosystems
    queries += [
        '"openclaw" skill',
        '"openclaw" mcp',
        '"voltagent" skill',
        '"claude" skill in:readme',
        '"anthropic" skill',
        '"github.com/ComposioHQ/awesome-claude-skills"',
        '"github.com/VoltAgent/awesome-agent-skills"',
        '"github.com/VoltAgent/awesome-openclaw-skills"',
    ]

    return queries


GITHUB_SEARCH_QUERIES = _build_queries()

# Target URLs
AWESOME_LIST_URLS = [
    # Agent Skills - Core
    "https://github.com/ComposioHQ/awesome-claude-skills",
    "https://github.com/VoltAgent/awesome-openclaw-skills",
    "https://github.com/VoltAgent/awesome-agent-skills",
    # Agent Skills - Newly Discovered
    "https://github.com/buainoai/awesome-clawdbot-skills",  # 565+ Clawdbot skills
    "https://github.com/natan89/awesome-openclaw-skills",  # 1,715+ community skills
    "https://github.com/mergisi/awesome-openclaw-agents",  # 162 production-ready templates
    "https://github.com/clawdbot-ai/awesome-openclaw-skills-zh",  # Chinese official
    "https://github.com/codeaashu/awesome-openclaw-Skills",
    "https://github.com/hesamsheikh/awesome-openclaw-usecases",
    "https://github.com/AlexAnys/awesome-openclaw-usecases-zh",
    # MCP Servers
    "https://github.com/punkpeye/awesome-mcp-servers",
    "https://github.com/yzfly/Awesome-MCP-ZH",
    "https://github.com/wong2/awesome-mcp-servers",
]

AGENT_SKILL_AWESOME_URLS = [
    "https://github.com/ComposioHQ/awesome-claude-skills",
    "https://github.com/VoltAgent/awesome-openclaw-skills",
    "https://github.com/VoltAgent/awesome-agent-skills",
    # New discovered awesome lists
    "https://github.com/buainoai/awesome-clawdbot-skills",  # 565+ Clawdbot skills
    "https://github.com/natan89/awesome-openclaw-skills",  # 1,715+ community skills
    "https://github.com/mergisi/awesome-openclaw-agents",  # 162 production-ready templates
    "https://github.com/clawdbot-ai/awesome-openclaw-skills-zh",  # Chinese official skills
    "https://github.com/codeaashu/awesome-openclaw-Skills",
    "https://github.com/hesamsheikh/awesome-openclaw-usecases",
    "https://github.com/AlexAnys/awesome-openclaw-usecases-zh",
]

MCP_AWESOME_URLS = [
    "https://github.com/punkpeye/awesome-mcp-servers",
    "https://github.com/yzfly/Awesome-MCP-ZH",
    "https://github.com/wong2/awesome-mcp-servers",
]

HUB_DIRECTORY_URLS = [
    "https://skills.sh/",
    "https://skills.sh/trending",
    "https://skills.sh/hot",
    "https://lobehub.com/zh/skills",
    "https://mcpservers.org/agent-skills",
    "https://lobehub.com/zh/mcp",
    "https://mcpmarket.com/zh",
    "https://mcpservers.org/",
    "https://mcpservers.org/all",
    "https://mcpservers.org/all?sort=newest",
]

MCPMARKET_LIST_PAGES = [
    "https://mcpmarket.com/zh/leaderboards",
    "https://mcpmarket.com/zh/tools/skills/leaderboard",
    "https://mcpmarket.com/zh/daily",
    "https://mcpmarket.com/zh/daily/skills",
]
