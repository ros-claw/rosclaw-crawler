#!/usr/bin/env python3
"""
第二轮清理 - 删除边界项目中的非物理硬件MCP
保留标准：实际控制物理硬件（机器人、传感器、执行器、工业设备）
删除标准：纯软件工具、游戏引擎、3D设计软件、仿真平台、网络工具
"""

import requests
import json
import re
import time
import os
from datetime import datetime

API_KEY = 'ROSCALW_KEY_PLACEHOLDER'
BASE_URL = 'https://www.rosclaw.io'
MCP_ENDPOINT = f'{BASE_URL}/api/mcp-packages'
HEADERS = {'Content-Type': 'application/json', 'X-API-Key': API_KEY}

PROGRESS_FILE = 'delete_progress_round2.json'

# === 明确保留的物理硬件MCP（白名单）===
KEEP_PATTERNS = [
    # ros-claw官方项目全部保留
    r'ros[\s\-_]?claw',
    # robotmcp官方项目
    r'robotmcp',
    # 明确硬件MCP - ROS/机器人
    r'ros[\s\-_]?mcp', r'ros2[\s\-_]?mcp', r'ros[\s\-_]?mcp[\s\-_]?server',
    r'Yutarop[\s\-_]?ros[\s\-_]?mcp', r'wise[\s\-_]?vision[\s\-_]?ros2',
    r'0xenesbayram[\s\-_]?ros2',
    # 明确硬件MCP - 工业控制
    r'beckhoff[\s\-_]?mcp', r'stamplc[\s\-_]?mcp', r'plc[\s\-_]?mcp[\s\-_]?server',
    r'OlubunmiAde[\s\-_]?plc', r'mwieczorkiewicz[\s\-_]?opcua',
    r'modbus[\s\-_]?mcp', r'KerberosClaw[\s\-_]?modbus',
    r'ezhuk[\s\-_]?modbus', r'cadugrillo[\s\-_]?s7',
    r'Manusevl[\s\-_]?mcp[\s\-_]?mqtt[\s\-_]?plc',
    r'Kluczekuba[\s\-_]?plc', r'Jancapboy[\s\-_]?industrial',
    r'eponce00[\s\-_]?tiaopen', r'rezasaadat1[\s\-_]?stamplc',
    r'vasiukoff[\s\-_]?mcprotocol',
    # 明确硬件MCP - 3D打印/CNC
    r'3dp[\s\-_]?mcp', r'brs077[\s\-_]?3dp',
    r'KlipperMCP', r'mikehatch[\s\-_]?klipper',
    r'bambu[\s\-_]?mcp', r'schwarztim[\s\-_]?bambu',
    r'synman[\s\-_]?bambu', r'griches[\s\-_]?bambu',
    r'DMontgomery40[\s\-_]?bambu', r'offthehook[\s\-_]?bambu',
    r'prusa[\s\-_]?mcp', r'gioelemo[\s\-_]?prusa',
    r'qidi[\s\-_]?printer', r'CSOAI[\s\-_]?ORG',
    r'VisualBoy[\s\-_]?3d[\s\-_]?printer',
    r'DMontgomery40[\s\-_]?3d[\s\-_]?printer',
    r'mcpflow[\s\-_]?dmontgomery40',
    r'WhitneyDesignLabs[\s\-_]?cnc',
    r'brs077[\s\-_]?cnc',
    # 明确硬件MCP - Arduino/ESP32/嵌入式
    r'arduino[\s\-_]?mcp', r'Volt23[\s\-_]?arduino',
    r'hardware[\s\-_]?mcp[\s\-_]?arduino',
    r'ESP32[\s\-_]?MCP', r'navado[\s\-_]?esp32',
    r'mcp[\s\-_]?esp32', r'adamdturner[\s\-_]?esp32',
    r'BNJ02[\s\-_]?Arduino', r'BNJ02[\s\-_]?MCP23017',
    r'golioth[\s\-_]?tinymcp',
    # 明确硬件MCP - 摄像头/传感器
    r'camera[\s\-_]?mcp', r'webcam[\s\-_]?mcp',
    r'u1f992[\s\-_]?camera', r'mattdeeds[\s\-_]?oak',
    r'sqrew[\s\-_]?rmcp[\s\-_]?camera',
    r'mamorett[\s\-_]?mcp[\s\-_]?camsnap',
    r'kmizu[\s\-_]?mcp[\s\-_]?web[\s\-_]?cam',
    r'openmv[\s\-_]?mcp', r'SingTown[\s\-_]?openmv',
    r'nordic[\s\-_]?thingy52',
    r'ruuvi[\s\-_]?mcp', r'juhapellotsalo',
    # 明确硬件MCP - 无人机
    r'drone[\s\-_]?mcp', r'0xKoda[\s\-_]?drone',
    r'dronelytics', r'markpdxt',
    r'uav[\s\-_]?mcp', r'Project[\s\-_]?GrADyS',
    r'tello[\s\-_]?mcp', r'linsun[\s\-_]?tello',
    r'MAVLink[\s\-_]?MCP', r'ion[\s\-_]?mavlink',
    r'Ryan[\s\-_]?Clinton[\s\-_]?drone',
    # 明确硬件MCP - 机器人/机械臂
    r'robot[\s\-_]?mcp', r'monteslu[\s\-_]?robot',
    r'IliaLarchenko[\s\-_]?robot',
    r'reachy[\s\-_]?mini', r'jackccrawford',
    r'nonead[\s\-_]?universal[\s\-_]?robots',
    r'aaaapoidesu[\s\-_]?mcpaicontrol',
    # 明确硬件MCP - 伺服/电机/LED
    r'servo[\s\-_]?mcp', r'd11r[\s\-_]?servo',
    r'Dew[\s\-_]?Demo[\s\-_]?Servo',
    r'mcp[\s\-_]?led', r'Starvern[\s\-_]?led',
    r'mcp[\s\-_]?motor', r'LGDiMaggio[\s\-_]?motor',
    # 明确硬件MCP - 通信协议
    r'serial[\s\-_]?mcp', r'bmdragos[\s\-_]?serial',
    r'zigbee[\s\-_]?mcp', r'LachlanB96',
    r'openthread[\s\-_]?mcp', r'swannman',
    r'mcp[\s\-_]?mqtt', r'openclawberlin',
    r'iot[\s\-_]?mcp', r'tkumata',
    r'mcp[\s\-_]?iot[\s\-_]?go', r'sukeesh',
    r'iot[\s\-_]?mcp[\s\-_]?bridge', r'francenylson1',
    r'iot[\s\-_]?mcp[\s\-_]?claude', r'monthop',
    # 明确硬件MCP - 其他硬件
    r'hardware[\s\-_]?mcp[\s\-_]?server',
    r'wenbox360[\s\-_]?hardware',
    r'NI[\s\-_]?Hardware[\s\-_]?MCP', r'JanGoebel',
    # 新增白名单
    r'^navado/esp32',
    r'^mikehatch/klipper',
    r'^cadugrillo/s7',
    r'^visualboy/mcp',
    r'^ion-g-ion/mavlink',
    r'^dmontgomery40/bambu',
    r'^dmontgomery40/mcp',
    r'^kukapay/opcua',
    r'^midhunxavier/opcua',
    r'^ekakit/lightfast',
    r'^macromnex/gromacs',
    r'^mushroomfleet/robot-team-discord-mcp',
    r'iot[\s\-_]?device[\s\-_]?mcp', r'AiAgentKarl',
    r'industrial[\s\-_]?mcp', r'lujin3',
    r'lg[\s\-_]?thermav', r'MarinX',
    r'dahua[\s\-_]?mcp', r'brianegge',
    r'beacon[\s\-_]?mcp', r'Showdown76py',
    r'yolink[\s\-_]?mcp', r'martydill',
    r'dgx[\s\-_]?spark', r'raibid[\s\-_]?labs',
    r'pixoo[\s\-_]?mcp', r'cyanheads',
    r'sigrok[\s\-_]?mcp', r'KenosInc',
    r'daedalus[\s\-_]?mcp[\s\-_]?sigrok',
    r'acap[\s\-_]?mcp', r'jrutanen',
    r'aws[\s\-_]?iot[\s\-_]?mcp', r'ag2[\s\-_]?mcp[\s\-_]?servers',
    r'attestable[\s\-_]?mcp', r'kontext[\s\-_]?security',
    r'rosbag[\s\-_]?mcp', r'cjh1995[\s\-_]?ros',
    r'mcp[\s\-_]?rosbags', r'binabik',
    r'mcpx[\s\-_]?mcp', r'YudaiKitamura',
    r'iota[\s\-_]?evm[\s\-_]?mcp', r'Danielmark001',
    r'acc[\s\-_]?mcp[\s\-_]?server', r'Acceleronix',
    r'ros[\s\-_]?mc[\s\-_]?server', r'surya7702',
    r'johneyesbot[\s\-_]?demorobot',
    r'lpigeon[\s\-_]?ros[\s\-_]?mcp',
    r'image[\s\-_]?scale[\s\-_]?robotmcp',
    # 精确owner/repo匹配
    r'^navado/esp32',
    r'^mikehatch/klipper',
    r'^cadugrillo/s7',
    r'^visualboy/mcp',
    r'^ion-g-ion/mavlink',
    r'^dmontgomery40/bambu',
    r'^dmontgomery40/mcp',
    r'^kukapay/opcua',
    r'^midhunxavier/opcua',
    r'^ekakit/lightfast',
    r'^macromnex/gromacs',
]

# === 第二轮删除规则：非物理硬件MCP ===
DELETE_PATTERNS = [
    # 游戏引擎（全部删除，即使是MCP server也不是物理硬件）
    r'unreal[\s\-_]?mcp', r'unity[\s\-_]?mcp', r'ue[\s\-_]?mcp', r'ue5[\s\-_]?mcp',
    r'ue[\s\-_]?blueprint', r'ue[\s\-_]?angelscript', r'ue[\s\-_]?spec',
    r'blender[\s\-_]?mcp', r'blender[\s\-_]?ai[\s\-_]?mcp', r'blender[\s\-_]?server',
    r'mcp[\s\-_]?blend', r'dcc[\s\-_]?mcp[\s\-_]?blender',
    r'genkit[\s\-_]?mcp[\s\-_]?client[\s\-_]?blender',
    # 3D设计/CAD软件（纯软件，无硬件控制）
    r'onshape[\s\-_]?mcp', r'solidedge[\s\-_]?mcp', r'rhino[\s\-_]?mcp',
    r'occt[\s\-_]?mcp', r'mged[\s\-_]?mcp', r'nsforge[\s\-_]?mcp',
    r'cadencely[\s\-_]?mcp', r'3d[\s\-_]?agent[\s\-_]?mcp',
    r'furniture[\s\-_]?designer[\s\-_]?mcp', r'kenchiku[\s\-_]?mcp',
    r'caddis[\s\-_]?mcp', r'tw[\s\-_]?cadastral[\s\-_]?mcp',
    r'photoshop[\s\-_]?mcp',
    # 仿真/CAE软件
    r'isaac[\s\-_]?sim[\s\-_]?mcp', r'gazebo[\s\-_]?mcp',
    r'paraview[\s\-_]?mcp', r'comsol[\s\-_]?mcp',
    r'openfoam[\s\-_]?mcp', r'ltspice[\s\-_]?mcp',
    r'tnavigator[\s\-_]?mcp', r'mcp[\s\-_]?scenario[\s\-_]?engine',
    # 纯软件工具/框架
    r'spring[\s\-_]?boot[\s\-_]?actuator',
    r'mcp[\s\-_]?ledger', r'jettyd[\s\-_]?mcp', r'dns[\s\-_]?tools[\s\-_]?mcp',
    r'mcp[\s\-_]?excel[\s\-_]?writer', r'idm[\s\-_]?mcp',
    r'shared[\s\-_]?memory[\s\-_]?mcp', r'private[\s\-_]?mcp',
    r'quantum[\s\-_]?resource[\s\-_]?estimator',
    r'autonomous[\s\-_]?cyber[\s\-_]?red[\s\-_]?team',
    # 网络/通信工具（非物理硬件）
    r'router[\s\-_]?mcp', r'scraper[\s\-_]?mcp',
    r'discord[\s\-_]?mcp', r'linebot[\s\-_]?mcp',
    # 成人/非机器人
    r'buttplug[\s\-_]?mcp',
    # 不明/无用
    r'rabi[\s\-_]?mcp', r'tt[\s\-_]?mcp', r'tymewear[\s\-_]?mcp',
    r'rigshare[\s\-_]?mcp', r'gogo[\s\-_]?mcp', r'cirklon[\s\-_]?mcp',
    r'debmatic[\s\-_]?mcp', r'node[\s\-_]?red[\s\-_]?contrib[\s\-_]?mcp',
    r'unimcp4cc', r'unity[\s\-_]?build[\s\-_]?automation',
    r'unity[\s\-_]?meta[\s\-_]?mcp', r'unity[\s\-_]?natural[\s\-_]?mcp',
    r'unity[\s\-_]?assistant[\s\-_]?mcp',
    r'mcp[\s\-_]?web[\s\-_]?cam', r'mcp[\s\-_]?web[\s\-_]?fetch',
    # 纯监控（无控制）
    r'hardware[\s\-_]?monitor[\s\-_]?mcp', r'system[\s\-_]?health[\s\-_]?mcp',
    # VR/AR（非物理硬件）
    r'mcp[\s\-_]?tools[\s\-_]?for[\s\-_]?vr',
    # 软件摄像头（无物理硬件接口）
    r'webcam[\s\-_]?mcp',
    # 学术/研究工具
    r'arxiv[\s\-_]?radar[\s\-_]?mcp', r'uc[\s\-_]?catalog[\s\-_]?mcp',
    r'uc[\s\-_]?mcp[\s\-_]?gen',
    # 其他纯软件
    r'lordicon[\s\-_]?mcp', r'iota[\s\-_]?mcp', r'evee[\s\-_]?mcp',
    r'agentbridge[\s\-_]?mcp', r'unify[\s\-_]?mcp', r'xlab[\s\-_]?mcp',
    r'nr[\s\-_]?mcp', r'lightfast[\s\-_]?mcp',
    r'mcp[\s\-_]?embedded[\s\-_]?ui', r'electron[\s\-_]?mcp',
    r'mnl[\s\-_]?mcp', r'mcp[\s\-_]?servo[\s\-_]?lock',
    r'geospatial[\s\-_]?tools[\s\-_]?mcp',
    r'drone[\s\-_]?uas[\s\-_]?regulatory[\s\-_]?intelligence',
    r'iot[\s\-_]?onvif[\s\-_]?mcp', r'geekhouse[\s\-_]?mcp',
    r'iot[\s\-_]?mcp[\s\-_]?claude', r'smart[\s\-_]?classroom[\s\-_]?mcp',
    r'home[\s\-_]?assistant[\s\-_]?vibecode', r'ha[\s\-_]?nexus[\s\-_]?agent',
    r'industrial[\s\-_]?events[\s\-_]?mcp',
    r'ot[\s\-_]?mcp[\s\-_]?guard', r'idfkit[\s\-_]?mcp',
    r'farcom[\s\-_]?mcp', r'ramp[\s\-_]?mcp',
    r'regennexus[\s\-_]?mcp', r'amber[\s\-_]?mcp',
    r'rosetta[\s\-_]?mcp', r'gromacs[\s\-_]?mcp',
    r'classic[\s\-_]?mac[\s\-_]?hardware',
    r'omni[\s\-_]?mcp',  # Dharit13/omni-mcp 不是omni-mcp/isaac-sim-mcp
    r'hanwha[\s\-_]?mcp', r'sensor[\s\-_]?tower[\s\-_]?mcp',
    r'mcp[\s\-_]?sigrok',
    r'advanced[\s\-_]?homeassistant[\s\-_]?mcp',
    r'ha[\s\-_]?mcp',  # zorak1103/ha-mcp
    r'mcp[\s\-_]?kvm',
    r'mcp[\s\-_]?iot[\s\-_]?go', r'mcp[\s\-_]?iot',
    r'homeassistant[\s\-_]?server[\s\-_]?mcp',
    r'homeassistant[\s\-_]?mcp',
    r'mcp[\s\-_]?homeassistant',
    r'ha[\s\-_]?linebot[\s\-_]?mcp',
    r'smart[\s\-_]?home[\s\-_]?mcp', r'smart[\s\-_]?home[\s\-_]?orchestrator',
    r'beacon[\s\-_]?mcp', r'dahua[\s\-_]?mcp',
    r'rosie[\s\-_]?mcp[\s\-_]?plugin',
    r'uc[\s\-_]?mcp', r'mcp[\s\-_]?cadquery',
    r'mcp[\s\-_]?3d[\s\-_]?printer[\s\-_]?server',
    r'prusa[\s\-_]?mcp', r'qidi[\s\-_]?printer[\s\-_]?mcp',
    r'cnc[\s\-_]?design[\s\-_]?control[\s\-_]?mcp',
    r'plc[\s\-_]?tools[\s\-_]?mcp', r'mcp[\s\-_]?mqtt[\s\-_]?plc',
    r'industrial[\s\-_]?agent[\s\-_]?mcp',
    r'ros2[\s\-_]?medkit[\s\-_]?mcp',
    r'mcp[\s\-_]?device[\s\-_]?server',
    r'robotics[\s\-_]?mcp',  # sandraschi/robotics-mcp
    r'robot[\s\-_]?team[\s\-_]?discord',
    r'mcp[\s\-_]?motor[\s\-_]?current',
    r'mcp[\s\-_]?cam', r'oak[\s\-_]?camera[\s\-_]?mcp',
    r'rmcp[\s\-_]?camera', r'mcp[\s\-_]?camsnap',
    r'macaroni[\s\-_]?pi[\s\-_]?mcpi',
    r'mcp[\s\-_]?servo',
    r'walk[\s\-_]?these[\s\-_]?ways',
    r'rl[\s\-_]?sar',
    r'ros[\s\-_]?mc[\s\-_]?server',
    r'lucid[\s\-_]?motors[\s\-_]?mcp',
    r'openmv[\s\-_]?mcp', r'camera[\s\-_]?mcp',
    r'mcp[\s\-_]?arduino[\s\-_]?server',
    r'arduino[\s\-_]?server[\s\-_]?mcp',
    r'mcp[\s\-_]?esp32[\s\-_]?firebase',
    r'esp32[\s\-_]?mcp[\s\-_]?server',
    r'starvern[\s\-_]?mcp[\s\-_]?led',
    r'd11r[\s\-_]?servo[\s\-_]?mcp',
    r'dew[\s\-_]?demo[\s\-_]?mcp[\s\-_]?servo[\s\-_]?lock',
    r'zigbee[\s\-_]?mcp', r'openthread[\s\-_]?mcp',
    r'mcp[\s\-_]?mqtt', r'iot[\s\-_]?mcp[\s\-_]?bridge',
    r'mavlink[\s\-_]?mcp', r'drone[\s\-_]?mcp',
    r'dronelytics[\s\-_]?mcp', r'uav[\s\-_]?mcp',
    r'tello[\s\-_]?mcp',
    r'reachy[\s\-_]?mini[\s\-_]?mcp',
    r'tinymcp',  # golioth/tinymcp
    r'mcpaicontrol[\s\-_]?rm65b',
    r'nonead[\s\-_]?universal[\s\-_]?robots',
    r'robot[\s\-_]?mcp',  # monteslu/robot-mcp
    r'robotmcp',  # robotmcp/robotmcp_client
    r'robot[\s\-_]?mcp',  # IliaLarchenko/robot_MCP
    r'beckhoff[\s\-_]?mcp',
    r'nordic[\s\-_]?thingy52[\s\-_]?mcp',
    r'webcam[\s\-_]?mcp',
    r'rosbag[\s\-_]?mcp',
    r'bambu[\s\-_]?mcp',
    r's7[\s\-_]?mcp[\s\-_]?bridge',
    r'modbus[\s\-_]?mcp', r'opcua[\s\-_]?mcp',
    r'plc[\s\-_]?mcp[\s\-_]?server', r'stamplc[\s\-_]?mcp',
    r'acc[\s\-_]?mcp[\s\-_]?server',
    r'iota[\s\-_]?evm[\s\-_]?mcp',
    r'mcpx[\s\-_]?mcp[\s\-_]?server',
    r'3dp[\s\-_]?mcp[\s\-_]?server',
    r'klipper[\s\-_]?mcp',
    r'kicad[\s\-_]?mcp',
    r'esp32[\s\-_]?mcp[\s\-_]?server',
    r'mcp[\s\-_]?rosbags',
    r'ros2[\s\-_]?mcp[\s\-_]?server',
    r'ros[\s\-_]?mcp',
    r'ros2[\s\-_]?mcp',
    r'unitree[\s\-_]?mujoco[\s\-_]?mcp',
    r'unitree[\s\-_]?sdk2[\s\-_]?mcp',
    r'librealsense[\s\-_]?mcp',
    r'inspire[\s\-_]?rh56[\s\-_]?mcp',
    r'ur[\s\-_]?rtde[\s\-_]?mcp',
    r'vicon[\s\-_]?datastream[\s\-_]?mcp',
    r'gcu[\s\-_]?gimbal[\s\-_]?mcp',
    r'rosclaw[\s\-_]?nav2[\s\-_]?mcp',
    r'rosclaw[\s\-_]?moveit2[\s\-_]?mcp',
    r'rosclaw[\s\-_]?vision[\s\-_]?mcp',
    r'g1[\s\-_]?isaac[\s\-_]?sim[\s\-_]?mcp',
    r'serial[\s\-_]?mcp',
    r'mcp[\s\-_]?modbus',
    r'mcprotocol[\s\-_]?modbus',
    r'farcom[\s\-_]?mcp[\s\-_]?pfc',
    r'tiaopen[\s\-_]?mcp',
    r'electronics[\s\-_]?mcp',
    r'mcp[\s\-_]?iot',
    r'mcp[\s\-_]?mqtt[\s\-_]?plc',
    r'plc[\s\-_]?tools[\s\-_]?mcp',
    r'industrial[\s\-_]?agent[\s\-_]?mcp',
    r's7[\s\-_]?mcp[\s\-_]?bridge',
    r'opcua4mcp',
    r'mcp[\s\-_]?opcua',
    r'cnc[\s\-_]?fluidnc[\s\-_]?mcp',
    r'cnc[\s\-_]?design[\s\-_]?control[\s\-_]?mcp',
    r'mcp[\s\-_]?3d[\s\-_]?printer[\s\-_]?server',
    r'prusa[\s\-_]?mcp',
    r'qidi[\s\-_]?printer[\s\-_]?mcp',
    r'bambu[\s\-_]?printer[\s\-_]?mcp',
    r'offthehook[\s\-_]?bambu[\s\-_]?printer',
    r'griches[\s\-_]?bambu[\s\-_]?mcp',
    r'synman[\s\-_]?bambu[\s\-_]?mcp',
    r'schwarztim[\s\-_]?bambu[\s\-_]?mcp',
    r'dmontgomery40[\s\-_]?bambu[\s\-_]?printer',
    r'dmontgomery40[\s\-_]?mcp[\s\-_]?3d[\s\-_]?printer',
    r'visualboy[\s\-_]?mcp[\s\-_]?3d[\s\-_]?printer',
    r'mcpflow[\s\-_]?dmontgomery40',
    r'arduino[\s\-_]?llm[\s\-_]?agent',
    r'volt23[\s\-_]?mcp[\s\-_]?arduino',
    r'arduino[\s\-_]?server[\s\-_]?mcp23017',
    r'mcp[\s\-_]?esp32[\s\-_]?firebase',
    r'esp32[\s\-_]?mcp[\s\-_]?server',
    r'starvern[\s\-_]?mcp[\s\-_]?led',
    r'd11r[\s\-_]?servo[\s\-_]?mcp',
    r'dew[\s\-_]?demo[\s\-_]?mcp[\s\-_]?servo[\s\-_]?lock',
    r'lachlanb96[\s\-_]?zigbee[\s\-_]?mcp',
    r'swannman[\s\-_]?openthread[\s\-_]?mcp',
    r'openclawberlin[\s\-_]?mcp[\s\-_]?mqtt',
    r'tkumata[\s\-_]?mcp[\s\-_]?iot',
    r'sukeesh[\s\-_]?mcp[\s\-_]?iot[\s\-_]?go',
    r'francenylson1[\s\-_]?iot[\s\-_]?mcp[\s\-_]?bridge',
    r'monthop[\s\-_]?iot[\s\-_]?mcp[\s\-_]?claude',
    r'ion[\s\-_]?mavlink',
    r'0xkoda[\s\-_]?drone[\s\-_]?mcp',
    r'markpdxt[\s\-_]?dronelytics[\s\-_]?mcp',
    r'project[\s\-_]?gradys[\s\-_]?uav[\s\-_]?mcp',
    r'linsun[\s\-_]?tello[\s\-_]?mcp',
    r'ryan[\s\-_]?clinton[\s\-_]?drone[\s\-_]?uas',
    r'jackccrawford[\s\-_]?reachy[\s\-_]?mini[\s\-_]?mcp',
    r'golioth[\s\-_]?tinymcp',
    r'aaaapoidesu[\s\-_]?mcpaicontrol[\s\-_]?rm65b',
    r'nonead[\s\-_]?nonead[\s\-_]?universal[\s\-_]?robots',
    r'monteslu[\s\-_]?robot[\s\-_]?mcp',
    r'robotmcp[\s\-_]?robotmcp[\s\-_]?client',
    r'IliaLarchenko[\s\-_]?robot[\s\-_]?mcp',
    r'ros[\s\-_]?claw[\s\-_]?rosclaw[\s\-_]?nav2',
    r'ros[\s\-_]?claw[\s\-_]?rosclaw[\s\-_]?moveit2',
    r'ros[\s\-_]?claw[\s\-_]?gcu[\s\-_]?gimbal',
    r'ros[\s\-_]?claw[\s\-_]?vicon[\s\-_]?datastream',
    r'ros[\s\-_]?claw[\s\-_]?unitree[\s\-_]?mujoco',
    r'ros[\s\-_]?claw[\s\-_]?unitree[\s\-_]?sdk2',
    r'ros[\s\-_]?claw[\s\-_]?librealsense',
    r'ros[\s\-_]?claw[\s\-_]?inspire[\s\-_]?rh56',
    r'ros[\s\-_]?claw[\s\-_]?ur[\s\-_]?rtde',
    r'ros[\s\-_]?claw[\s\-_]?g1[\s\-_]?isaac[\s\-_]?sim',
    r'ros[\s\-_]?claw[\s\-_]?rosclaw[\s\-_]?vision',
]

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {'deleted_ids': [], 'failed_ids': [], 'kept_ids': []}

def save_progress(progress):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

def get_all_items():
    resp = requests.get(f'{MCP_ENDPOINT}?page=1&limit=1000', headers=HEADERS, timeout=30)
    data = resp.json()
    return data if isinstance(data, list) else data.get('items', data.get('data', []))

def classify_item(item):
    """返回: 'keep', 'delete', 'review'"""
    name = item.get('name', '').lower()
    url = item.get('githubRepoUrl', '').lower()
    text = f'{name} {url}'
    
    # 提取owner和repo用于更精确匹配
    owner_repo = ''
    if 'github.com/' in url:
        parts = url.split('github.com/')[-1].split('/')
        if len(parts) >= 2:
            owner_repo = f'{parts[0]}/{parts[1]}'.lower()
    
    # 1. 先检查白名单（保留）- 检查name、url、owner_repo
    for pattern in KEEP_PATTERNS:
        if re.search(pattern, text) or re.search(pattern, owner_repo):
            return 'keep', f'Whitelist: {pattern}'
    
    # 2. 检查删除规则
    for pattern in DELETE_PATTERNS:
        if re.search(pattern, text):
            return 'delete', f'Delete pattern: {pattern}'
    
    # 3. 默认保留（需要人工review）
    return 'review', 'Needs manual review'

def delete_item(item_id):
    try:
        resp = requests.delete(f'{MCP_ENDPOINT}?id={item_id}', headers=HEADERS, timeout=30)
        return resp.status_code in [200, 201, 204], resp.status_code
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 60)
    print("ROSClaw 第二轮清理 - 边界项目严格筛选")
    print("=" * 60)
    
    progress = load_progress()
    deleted_ids = set(progress['deleted_ids'])
    
    items = get_all_items()
    print(f"\n当前网站: {len(items)} 个MCP包")
    
    # 分类
    to_delete = []
    to_keep = []
    to_review = []
    
    for item in items:
        if item['id'] in deleted_ids:
            continue
        
        result, reason = classify_item(item)
        item['_result'] = result
        item['_reason'] = reason
        
        if result == 'delete':
            to_delete.append(item)
        elif result == 'keep':
            to_keep.append(item)
        else:
            to_review.append(item)
    
    print(f"\n分类结果:")
    print(f"  ✅ 保留（白名单）: {len(to_keep)}")
    print(f"  ❌ 删除（非硬件）: {len(to_delete)}")
    print(f"  ⚠️  需人工确认: {len(to_review)}")
    
    # 打印待删除样本
    print(f"\n=== 待删除样本（前20个）===")
    for item in to_delete[:20]:
        print(f"  ❌ {item['name']} | {item.get('githubRepoUrl', '')}")
    if len(to_delete) > 20:
        print(f"  ... 还有 {len(to_delete)-20} 个")
    
    # 打印保留样本
    print(f"\n=== 保留样本 ===")
    for item in to_keep[:20]:
        print(f"  ✅ {item['name']} | {item.get('githubRepoUrl', '')}")
    if len(to_keep) > 20:
        print(f"  ... 还有 {len(to_keep)-20} 个")
    
    # 打印需确认样本
    print(f"\n=== 需人工确认样本 ===")
    for item in to_review[:20]:
        print(f"  ⚠️  {item['name']} | {item.get('githubRepoUrl', '')}")
    if len(to_review) > 20:
        print(f"  ... 还有 {len(to_review)-20} 个")
    
    # 询问是否执行删除
    print(f"\n{'='*60}")
    print(f"准备删除 {len(to_delete)} 个非硬件MCP项目")
    print(f"保留 {len(to_keep)} 个物理硬件MCP项目")
    print(f"{len(to_review)} 个项目需要人工确认")
    print(f"\n如需执行删除，请运行: python3 delete_round2.py --execute")
    
    # 保存分类报告
    report = {
        'timestamp': datetime.now().isoformat(),
        'total': len(items),
        'keep': [{'name': i['name'], 'url': i.get('githubRepoUrl', ''), 'reason': i['_reason']} for i in to_keep],
        'delete': [{'name': i['name'], 'url': i.get('githubRepoUrl', ''), 'reason': i['_reason']} for i in to_delete],
        'review': [{'name': i['name'], 'url': i.get('githubRepoUrl', ''), 'reason': i['_reason']} for i in to_review],
    }
    with open('round2_classification.json', 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n📄 分类报告已保存: round2_classification.json")

def execute_delete():
    progress = load_progress()
    deleted_ids = set(progress['deleted_ids'])
    
    items = get_all_items()
    to_delete = []
    
    for item in items:
        if item['id'] in deleted_ids:
            continue
        result, _ = classify_item(item)
        if result == 'delete':
            to_delete.append(item)
    
    print(f"\n执行删除: {len(to_delete)} 个项目")
    
    success = 0
    failed = 0
    
    for i, item in enumerate(to_delete, 1):
        item_id = item['id']
        name = item['name']
        
        print(f"\n[{i}/{len(to_delete)}] {name}")
        
        ok, code = delete_item(item_id)
        if ok:
            success += 1
            progress['deleted_ids'].append(item_id)
            print(f"  ✅ 删除成功 ({code})")
        else:
            failed += 1
            progress['failed_ids'].append(item_id)
            print(f"  ❌ 删除失败 ({code})")
        
        save_progress(progress)
        
        if i % 5 == 0:
            time.sleep(2)
        else:
            time.sleep(0.5)
    
    print(f"\n{'='*60}")
    print("第二轮清理完成!")
    print(f"成功: {success}, 失败: {failed}")
    
    remaining = get_all_items()
    print(f"剩余MCP: {len(remaining)}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--execute':
        execute_delete()
    else:
        main()
