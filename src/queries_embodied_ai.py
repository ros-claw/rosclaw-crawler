"""
Comprehensive query list for embodied AI / robotics / physical AI MCPs and Skills
"""

# Humanoid robots
HUMANOID_QUERIES = [
    'mcp-server humanoid robot',
    'mcp-server optimus robot',
    'mcp-server figure robot',
    'mcp-server atlas robot',
    'mcp-server digit robot',
    'mcp-server cassie robot',
    'mcp-server anymal robot',
    'mcp-server spot robot',
    'mcp-server boston dynamics',
    'mcp-server unitree robot',
    'mcp-server tesla bot',
    'mcp-server pepper robot',
    'mcp-server nao robot',
    'mcp-server romeo robot',
    'mcp-server jibo robot',
    'mcp-server opencat robot',
    'mcp-server spotmicro robot',
]

# Industrial robots
INDUSTRIAL_QUERIES = [
    'mcp-server industrial robot',
    'mcp-server factory automation',
    'mcp-server cobot',
    'mcp-server kuka robot',
    'mcp-server abb robot',
    'mcp-server fanuc robot',
    'mcp-server yaskawa robot',
    'mcp-server motoman robot',
    'mcp-server staubli robot',
    'mcp-server omron robot',
    'mcp-server mitsubishi robot',
    'mcp-server siemens plc',
    'mcp-server rockwell automation',
    'mcp-server schneider electric',
    'mcp-server beckhoff',
    'mcp-server festo',
]

# Drones
DRONE_QUERIES = [
    'mcp-server drone',
    'mcp-server uav',
    'mcp-server px4',
    'mcp-server mavlink',
    'mcp-server dji',
    'mcp-server drone swarm',
    'mcp-server aerial robot',
]

# Simulation
SIMULATION_QUERIES = [
    'mcp-server mujoco',
    'mcp-server gazebo',
    'mcp-server isaac sim',
    'mcp-server pybullet',
    'mcp-server webots',
    'mcp-server carla',
    'mcp-server lgsvl',
    'mcp-server apollo',
    'mcp-server autoware',
]

# ROS ecosystem
ROS_QUERIES = [
    'mcp-server ros2',
    'mcp-server ros2 control',
    'mcp-server ros2 navigation',
    'mcp-server ros2 perception',
    'mcp-server moveit',
    'mcp-server nav2',
    'mcp-server slam toolbox',
    'mcp-server rosbridge',
    'mcp-server foxglove',
]

# Sensors
SENSOR_QUERIES = [
    'mcp-server lidar',
    'mcp-server depth camera',
    'mcp-server imu',
    'mcp-server force sensor',
    'mcp-server tactile sensor',
    'mcp-server proximity sensor',
    'mcp-server camera robot',
]

# Control
CONTROL_QUERIES = [
    'mcp-server model predictive control',
    'mcp-server optimal control',
    'mcp-server adaptive control',
    'mcp-server robust control',
    'mcp-server nonlinear control',
    'mcp-server reinforcement learning robot',
    'mcp-server imitation learning robot',
    'mcp-server sim2real',
    'mcp-server domain randomization',
]

# Medical/Rehabilitation
MEDICAL_QUERIES = [
    'mcp-server surgical robot',
    'mcp-server medical robot',
    'mcp-server rehabilitation robot',
    'mcp-server exoskeleton',
    'mcp-server prosthetic',
    'mcp-server bionic',
]

# Mobile robots
MOBILE_QUERIES = [
    'mcp-server agv',
    'mcp-server amr',
    'mcp-server mobile robot',
    'mcp-server warehouse robot',
    'mcp-server logistics robot',
    'mcp-server cleaning robot',
    'mcp-server inspection robot',
]

# Soft robots
SOFT_QUERIES = [
    'mcp-server soft robot',
    'mcp-server continuum robot',
    'mcp-server snake robot',
    'mcp-server modular robot',
    'mcp-server self-reconfigurable',
]

# Swarm/Multi-robot
SWARM_QUERIES = [
    'mcp-server swarm robotics',
    'mcp-server multi-robot',
    'mcp-server robot fleet',
    'mcp-server collective robot',
]

# 3D Printing
PRINTING_QUERIES = [
    'mcp-server 3d printer',
    'mcp-server 3d printing',
    'mcp-server cnc',
    'mcp-server laser cutter',
]

# Skills
SKILL_QUERIES = [
    'claude skill robot',
    'claude skill robotics',
    'agent skill robot manipulation',
    'agent skill robot navigation',
    'skill.md embodied ai',
    'skill.md robotics',
    'skill.md robot',
]

# Combine all queries
ALL_QUERIES = (
    HUMANOID_QUERIES +
    INDUSTRIAL_QUERIES +
    DRONE_QUERIES +
    SIMULATION_QUERIES +
    ROS_QUERIES +
    SENSOR_QUERIES +
    CONTROL_QUERIES +
    MEDICAL_QUERIES +
    MOBILE_QUERIES +
    SOFT_QUERIES +
    SWARM_QUERIES +
    PRINTING_QUERIES +
    SKILL_QUERIES
)

print(f"Total queries: {len(ALL_QUERIES)}")
