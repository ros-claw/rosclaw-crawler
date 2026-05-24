"""
Deep Crawl Queries - Extended search terms for comprehensive coverage
"""

# Core robotics terms
CORE_ROBOTICS = [
    'mcp-server ros',
    'mcp-server ros2',
    'mcp-server robot',
    'mcp-server robotics',
    'mcp-server embodied',
    'mcp-server physical ai',
]

# Robot platforms
PLATFORMS = [
    'mcp-server unitree',
    'mcp-server boston dynamics',
    'mcp-server spot robot',
    'mcp-server go2 robot',
    'mcp-server g1 humanoid',
    'mcp-server atlas robot',
    'mcp-server digit robot',
    'mcp-server pepper robot',
    'mcp-server nao robot',
    'mcp-server turtlebot',
    'mcp-server kinova',
    'mcp-server franka',
    'mcp-server ur5',
    'mcp-server ur10',
    'mcp-server universal robot',
]

# Simulation
SIMULATION = [
    'mcp-server mujoco',
    'mcp-server gazebo',
    'mcp-server isaac sim',
    'mcp-server isaac lab',
    'mcp-server pybullet',
    'mcp-server webots',
    'mcp-server CoppeliaSim',
    'mcp-server vrep',
    'mcp-server carla',
    'mcp-server lgsvl',
    'mcp-server airsim',
    'mcp-server habitat',
    'mcp-server sapien',
    'mcp-server maniskill',
    'mcp-server robosuite',
]

# Drones
DRONES = [
    'mcp-server drone',
    'mcp-server uav',
    'mcp-server px4',
    'mcp-server ardupilot',
    'mcp-server mavlink',
    'mcp-server dji',
    'mcp-server tello',
    'mcp-server crazyflie',
]

# Control & Planning
CONTROL = [
    'mcp-server navigation',
    'mcp-server slam',
    'mcp-server path planning',
    'mcp-server motion planning',
    'mcp-server trajectory',
    'mcp-server mpc',
    'mcp-server model predictive control',
    'mcp-server reinforcement learning robot',
    'mcp-server imitation learning robot',
    'mcp-server sim2real',
    'mcp-server domain randomization',
]

# Vision & Perception
VISION = [
    'mcp-server computer vision robot',
    'mcp-server perception robot',
    'mcp-server object detection robot',
    'mcp-server segmentation robot',
    'mcp-server depth estimation',
    'mcp-server point cloud',
    'mcp-server lidar',
    'mcp-server realsense',
    'mcp-server camera robot',
]

# Manipulation
MANIPULATION = [
    'mcp-server grasping',
    'mcp-server manipulation',
    'mcp-server gripper',
    'mcp-server dexterous',
    'mcp-server hand tracking',
    'mcp-server pick and place',
    'mcp-server assembly robot',
]

# Industrial
INDUSTRIAL = [
    'mcp-server factory',
    'mcp-server industrial',
    'mcp-server automation',
    'mcp-server plc',
    'mcp-server cobot',
    'mcp-server kuka',
    'mcp-server abb',
    'mcp-server fanuc',
    'mcp-server yaskawa',
]

# 3D Printing
PRINTING = [
    'mcp-server 3d printer',
    'mcp-server bambu',
    'mcp-server prusa',
    'mcp-server klipper',
    'mcp-server octoprint',
    'mcp-server cnc',
    'mcp-server laser cutter',
]

# IoT & Hardware
IOT = [
    'mcp-server arduino',
    'mcp-server esp32',
    'mcp-server raspberry pi robot',
    'mcp-server jetson',
    'mcp-server modbus',
    'mcp-server mqtt robot',
    'mcp-server sensor',
    'mcp-server actuator',
    'mcp-server servo',
    'mcp-server motor',
]

# Skills
SKILLS = [
    'skill.md robot',
    'skill.md robotics',
    'skill.md ros',
    'skill.md ros2',
    'skill.md drone',
    'skill.md manipulation',
    'skill.md navigation',
    'claude skill robot',
    'claude skill robotics',
    'agent skill robot',
]

# Combine all
ALL_QUERIES = (
    CORE_ROBOTICS +
    PLATFORMS +
    SIMULATION +
    DRONES +
    CONTROL +
    VISION +
    MANIPULATION +
    INDUSTRIAL +
    PRINTING +
    IOT +
    SKILLS
)

print(f"Total deep crawl queries: {len(ALL_QUERIES)}")
