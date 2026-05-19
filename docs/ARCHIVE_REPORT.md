# ROSClaw Crawler — 归档整理报告

> **归档时间**: 2026-05-18
> **归档人**: 他妈的 🤖
> **原始目录**: `/home/ubuntu/.openclaw/workspace/rosclaw_crawler`

---

## 📁 目录结构

```
rosclaw_crawler/
├── src/              # 核心源代码（保留）
├── archive/          # 历史归档
│   ├── scripts/      # 所有历史脚本
│   ├── logs/         # 所有日志文件
│   ├── data/         # 数据库、JSON、CSV
│   └── reports/      # Markdown 报告
├── docs/             # 文档（新建）
└── assets/           # 静态资源（预留）
```

---

## 🎯 项目概述

ROSClaw Crawler 是一个 **Hardware MCP (Model Context Protocol) 项目发现与审核系统**，用于：

1. **爬取** GitHub 上的 MCP 服务器项目
2. **分类** 物理硬件相关 vs 纯软件/仿真项目
3. **LLM 分析** 项目质量与硬件控制真实性
4. **批量上传** 到技能市场（如 skills.sh）
5. **严格审核** 删除非物理硬件项目

---

## 🔧 核心配置

### API 密钥（已归档，注意保密）
- **GitHub Token**: `GITHUB_TOKEN_PLACEHOLDER`
- **Google Cloud API**: `AIzaSyCX_EhVhxG6BiVQ1yZ6Fa6SkNrAYBuJidE`
- **LLM API**: Kimi Coding API (`https://api.kimi.com/coding/`)
- **代理**: `socks5h://127.0.0.1:1080` (hysteria)

### 关键词矩阵（中英双语）
- **核心具身智能**: Embodied AI, 具身智能, Physical AI, 物理AI
- **模型范式**: VLA, VLN, World Models, LLM Robot Control
- **感知空间**: SLAM, NeRF, 3DGS, Sensor Fusion
- **仿真控制**: Sim-to-Real, MuJoCo, Isaac Sim, ROS2, Gazebo
- **工业硬件**: Industrial Automation, IoT, Jetson, Raspberry Pi

---

## 📊 关键成果

### 数据规模
- **总爬取项目**: ~500+ MCP 服务器
- **物理硬件相关**: 178 个（严格审核后保留）
- **删除非硬件项目**: 221 个（七轮清理）

### 分类统计（178个保留项目）
| 类别 | 数量 | 示例 |
|------|------|------|
| ROS2/机器人 | ~40 | ros-mcp, turtlebot, moveit, reachy |
| 工业控制 | ~30 | PLC, Modbus, OPCUA, Beckhoff, S7, CNC |
| 3D打印 | ~15 | Klipper, Bambu, Prusa, 3DP |
| 传感器/物联网 | ~25 | Arduino, ESP32, BLE, Zigbee |
| 摄像头/视觉 | ~10 | Webcam, OpenMV, RealSense |
| 无人机/车辆 | ~8 | Drone, MAVLink, Unitree |
| 其他硬件 | ~50 | 各种专用硬件接口 |

---

## 🧹 七轮清理历程

| 轮次 | 删除数量 | 原因 | 累计删除 |
|------|----------|------|----------|
| 第一轮 | 111 | 明显非MCP（游戏引擎、纯软件工具） | 111 |
| 第二轮 | 30 | 边界非硬件（仿真软件、可视化工具） | 141 |
| 第三轮 | 49 | review项目（需人工确认） | 190 |
| 第四轮 | 4 | 最终review（边界案例） | 194 |
| 第五轮 | 19 | 手动确认（非物理硬件） | 213 |
| 第六轮 | 2 | 仿真软件（遗漏） | 215 |
| 第七轮 | 6 | 最终边界（严格筛选） | **221** |

**最终保留**: 178 个纯物理硬件 MCP 项目

---

## 🛠️ 核心脚本说明

### 爬虫阶段
| 脚本 | 功能 |
|------|------|
| `phase1_awesome_lists.py` | 爬取 Awesome Lists（Composio, VoltAgent 等） |
| `phase2_hub_directories.py` | 爬取 Hub 目录（skills.sh, lobehub 等） |
| `phase2b_mcpmarket.py` | 爬取 MCP Market 排行榜 |
| `phase3_github_search.py` | GitHub 高级搜索（MCP + 硬件关键词） |
| `continuous_crawler.py` | 持续监控新仓库 |
| `deep_crawl.py` | 深度爬取（递归发现） |
| `targeted_crawl.py` | 定向爬取特定用户/组织 |

### 分析阶段
| 脚本 | 功能 |
|------|------|
| `llm_analyzer.py` | LLM 单条分析 |
| `llm_analyzer_batch.py` | 批量 LLM 分析 |
| `llm_batch_annotate.py` | 批量标注 |
| `llm_parallel_annotate.py` | 并行标注 |
| `strict_analyze.py` | 严格模式分析 |
| `analyze_batch.py` | 批量分析结果汇总 |

### 清理阶段
| 脚本 | 功能 |
|------|------|
| `strict_mcp_cleanup.py` | 严格清理主脚本 |
| `delete_fake_mcp.py` | 删除假 MCP |
| `delete_round2.py` ~ `delete_round7.py` | 各轮清理脚本 |
| `bulk_delete.py` | 批量删除 |
| `strict_review.py` | 严格审核 |
| `batch_strict_review.py` | 批量严格审核 |

### 上传阶段
| 脚本 | 功能 |
|------|------|
| `bulk_upload.py` | 批量上传到 skills.sh |
| `bulk_upload_strict.py` | 严格模式上传 |
| `generate_upload_list.py` | 生成上传列表 |

### 数据库工具
| 脚本 | 功能 |
|------|------|
| `database.py` | SQLite 数据库操作 |
| `db_helper.py` | 数据库辅助函数 |
| `enhance_db.py` | 数据库增强 |

---

## 💡 关键经验教训

### 1. LLM API 限制
- Kimi Coding API **仅限 Coding Agents 使用**（403 错误）
- 需要通用 Moonshot API Key 或 OpenAI-compatible Key
- 已配置到 `config.py` 但无法直接调用

### 2. 审核策略
- **白名单机制**: 178 个核心硬件项目作为基准
- **自动关键词验证**: ROS/PLC/Arduino/传感器等
- **删除规则**: 游戏引擎、仿真软件、纯工具类
- **人工审核**: 边界项目需逐个确认

### 3. 数据质量
- 大量项目名为 "MCP" 但实际不实现 MCP 协议
- 很多是游戏/仿真/可视化，非物理硬件控制
- 需要验证 README、代码、实际硬件接口

### 4. 上传注意事项
- 必须包含 `submolt` + `submolt_name`
- **绝对不能**使用 `tags` 字段（403 错误）
- 验证机制: 数学题挑战，答案格式 "XX.00"

---

## 🔗 相关资源

### Awesome Lists 来源
- [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills)
- [VoltAgent/awesome-openclaw-skills](https://github.com/VoltAgent/awesome-openclaw-skills)
- [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)
- [yzfly/Awesome-MCP-ZH](https://github.com/yzfly/Awesome-MCP-ZH)

### Hub 目录
- [skills.sh](https://skills.sh/)
- [lobehub.com/zh/skills](https://lobehub.com/zh/skills)
- [mcpservers.org](https://mcpservers.org/)
- [mcpmarket.com](https://mcpmarket.com/)

---

## 📁 归档文件清单

### archive/scripts/ (全部 Python/Shell 脚本)
- 总计: ~80 个脚本
- 涵盖: 爬虫、分析、清理、上传、数据库工具

### archive/logs/ (全部日志文件)
- `*.log`: 17 个日志文件（标注、爬虫、清理过程）
- `*.out`: 输出文件（标注结果、分类结果）
- `*.txt`: 上传批次列表

### archive/data/ (数据文件)
- `rosclaw_hub.db`: 主数据库（SQLite）
- `rosclaw_all_llm_annotations.json`: LLM 标注数据
- `top500_mcp_skill.json`: Top 500 MCP 技能
- `voltagent_skills.json`: VoltAgent 技能数据
- `delete_progress*.json`: 各轮清理进度
- `round*_classification.json`: 各轮分类结果

### archive/reports/ (报告文件)
- `final_report.md`: 最终清理报告
- `final_summary.md`: 最终摘要
- `llm_analysis_report.md`: LLM 分析报告

---

## 🚀 未来建议

1. **自动化审核**: 建立 CI/CD 流程，新上传项目自动验证
2. **月度清理**: 每月运行一次清理脚本
3. **社区贡献**: 开放白名单更新机制
4. **LLM 升级**: 解决 Kimi API 限制，使用通用模型
5. **多语言支持**: 扩展中文/日文/韩文关键词矩阵
6. **硬件测试**: 对保留项目进行实际硬件验证

---

## 📝 备注

- 所有 API Key 已记录在 `src/config.py`，**注意保密**
- 数据库文件包含完整爬取历史，可用于分析趋势
- 日志文件记录了完整的调试过程，可供排错参考

---

*归档完成。所有历史文件已分类整理，核心脚本保留在 `src/` 目录。*
