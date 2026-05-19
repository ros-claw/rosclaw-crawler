# ROSClaw Crawler — 项目归档总结

> **归档时间**: 2026-05-18 14:35
> **归档人**: 他妈的 🤖

---

## ✅ 整理完成

### 目录结构

```
rosclaw_crawler/
├── src/                    # 60 个核心脚本（保留）
│   ├── config.py           # 配置：API密钥、关键词矩阵
│   ├── phase1_awesome_lists.py    # 爬取 Awesome Lists
│   ├── phase2_hub_directories.py  # 爬取 Hub 目录
│   ├── phase3_github_search.py    # GitHub 高级搜索
│   ├── llm_analyzer*.py    # LLM 分析脚本（5个）
│   ├── strict_mcp_cleanup.py    # 严格清理主脚本
│   ├── delete_round*.py    # 各轮清理脚本（6个）
│   ├── bulk_upload*.py     # 批量上传脚本
│   └── ...
│
├── archive/                # 历史归档（159 个文件）
│   ├── scripts/            # 63 个历史脚本
│   ├── logs/               # 55 个日志文件
│   ├── data/               # 34 个数据文件（DB/JSON/CSV）
│   └── reports/            # 5 个 Markdown 报告
│
├── docs/                   # 2 个文档
│   ├── ARCHIVE_REPORT.md   # 完整归档报告
│   └── README.md           # 快速索引
│
└── assets/                 # 静态资源（预留）
```

---

## 📊 关键数据

| 指标 | 数值 |
|------|------|
| **总文件数** | 219 个 |
| **核心脚本** | 60 个（src/） |
| **历史归档** | 159 个（archive/） |
| **爬取项目** | ~500+ MCP 服务器 |
| **保留项目** | **178 个** 物理硬件 MCP |
| **删除项目** | **221 个** 非硬件/仿真项目 |
| **清理轮次** | 7 轮严格审核 |

---

## 🎯 核心成果

### 178 个保留项目分类

| 类别 | 数量 | 示例 |
|------|------|------|
| ROS2/机器人 | ~40 | ros-mcp, turtlebot, moveit, reachy |
| 工业控制 | ~30 | PLC, Modbus, OPCUA, Beckhoff, S7, CNC |
| 3D打印 | ~15 | Klipper, Bambu, Prusa, 3DP |
| 传感器/物联网 | ~25 | Arduino, ESP32, BLE, Zigbee, OpenThread |
| 摄像头/视觉 | ~10 | Webcam, OpenMV, RealSense |
| 无人机/车辆 | ~8 | Drone, MAVLink, Unitree |
| 其他硬件 | ~50 | 各种专用硬件接口 |

---

## 🧹 七轮清理历程

| 轮次 | 删除 | 原因 | 累计 |
|------|------|------|------|
| 1 | 111 | 明显非MCP（游戏引擎、纯软件） | 111 |
| 2 | 30 | 边界非硬件（仿真、可视化） | 141 |
| 3 | 49 | review项目（需人工确认） | 190 |
| 4 | 4 | 最终review（边界案例） | 194 |
| 5 | 19 | 手动确认（非物理硬件） | 213 |
| 6 | 2 | 仿真软件（遗漏） | 215 |
| 7 | 6 | 最终边界（严格筛选） | **221** |

---

## 💡 关键经验教训

1. **API 限制**: Kimi Coding API 仅限 Coding Agents，需通用 Moonshot API
2. **审核策略**: 白名单 + 自动关键词验证 + 人工审核边界项目
3. **数据质量**: 大量项目名为"MCP"但实际不实现 MCP 协议
4. **上传规则**: 必须含 `submolt` + `submolt_name`，禁用 `tags`

---

## 📁 重要文件位置

| 文件 | 路径 | 说明 |
|------|------|------|
| 核心配置 | `src/config.py` | API密钥、关键词矩阵 |
| 主数据库 | `archive/data/rosclaw_hub.db` | SQLite，完整爬取历史 |
| LLM标注 | `archive/data/rosclaw_all_llm_annotations.json` | 全部分析结果 |
| Top500技能 | `archive/data/top500_mcp_skill.json` | 精选项目 |
| 完整报告 | `docs/ARCHIVE_REPORT.md` | 详细归档文档 |

---

## 🚀 后续建议

1. **自动化审核**: 建立 CI/CD，新上传自动验证
2. **月度清理**: 每月运行清理脚本
3. **LLM升级**: 解决 API 限制，使用通用模型
4. **硬件测试**: 对保留项目进行实际硬件验证
5. **社区开放**: 开放白名单更新机制

---

*归档完成。所有 219 个文件已分类整理。*
