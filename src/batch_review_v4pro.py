#!/usr/bin/env python3
"""
批量处理剩余未标注仓库 - DeepSeek v4-pro
只审核+分类，API上传标记为pending_api
"""
import sqlite3
import json
import time
import asyncio
import aiohttp
import logging
from datetime import datetime
from pathlib import Path
from config import DB_PATH

# 日志配置
LOG_FILE = Path(__file__).parent / "batch_review_v4pro.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# DeepSeek API配置
API_BASE = "https://api.deepseek.com"
API_KEY = ""${DEEPSEEK_API_KEY}""
MODEL = "deepseek-v4-pro"
CONCURRENCY = 3  # v4-pro较慢，降低并发

SYSTEM_PROMPT = """你是一个专业的具身智能/机器人领域分析助手。
请分析给定的GitHub仓库信息，输出以下字段（JSON格式）：

- llm_summary: 一句话中文总结（30字以内），说明这个仓库的核心功能和价值
- llm_relevance_score: 与具身智能/机器人/物理AI的相关性评分（1-10，10最相关）
- llm_category: 分类标签，从以下选择最匹配的一个：
  机器人控制、仿真平台、感知算法、VLA模型、世界模型、
  强化学习、模仿学习、SLAM/3D重建、硬件接口、遥操作、
  多模态交互、开发工具、数据集、其他
- llm_key_features: 3个以内的关键特性，用逗号分隔的中文短语

只输出JSON，不要其他内容。"""

semaphore = asyncio.Semaphore(CONCURRENCY)


async def analyze_repo(session: aiohttp.ClientSession, repo_id: int, name: str, description: str, domain_tags: str, stars: int) -> dict:
    """调用DeepSeek API分析单个仓库"""
    async with semaphore:
        desc = description or "无描述"
        tags = ""
        try:
            if domain_tags:
                tags_data = json.loads(domain_tags)
                if isinstance(tags_data, list):
                    tags = ", ".join(tags_data)
        except:
            tags = domain_tags or ""

        prompt = f"""仓库名称: {name}
Star数: {stars}
描述: {desc}
领域标签: {tags}

请分析这个仓库。"""

        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 300,
            "response_format": {"type": "json_object"}
        }

        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with session.post(
                    f"{API_BASE}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    if resp.status == 429:
                        wait = 2 ** attempt
                        logger.warning(f"Repo {repo_id} rate limited, retry in {wait}s")
                        await asyncio.sleep(wait)
                        continue

                    resp.raise_for_status()
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    result = json.loads(content)

                    return {
                        "repo_id": repo_id,
                        "success": True,
                        "llm_summary": result.get("llm_summary", "")[:100],
                        "llm_relevance_score": min(10, max(1, int(result.get("llm_relevance_score", 5)))),
                        "llm_category": result.get("llm_category", "其他")[:64],
                        "llm_key_features": result.get("llm_key_features", "")[:200],
                        "raw": content
                    }
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(f"Repo {repo_id} attempt {attempt+1} failed: {e}, retry in {wait}s")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Repo {repo_id} failed after {max_retries} attempts: {e}")
                    return {
                        "repo_id": repo_id,
                        "success": False,
                        "error": str(e)
                    }

        return {"repo_id": repo_id, "success": False, "error": "max retries exceeded"}


def update_database(results: list):
    """批量更新数据库 - 标记为pending_api"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    success_count = 0
    fail_count = 0

    for r in results:
        if r["success"]:
            try:
                cursor.execute("""
                    UPDATE rosclaw_hub_resources
                    SET llm_summary = ?,
                        llm_relevance_score = ?,
                        llm_category = ?,
                        llm_key_features = ?,
                        llm_analyzed_at = ?,
                        llm_model = ?,
                        llm_upload_status = 'pending_api'
                    WHERE id = ?
                """, (
                    r.get("llm_summary", ""),
                    r.get("llm_relevance_score", 5),
                    r.get("llm_category", "其他"),
                    r.get("llm_key_features", ""),
                    now,
                    MODEL,
                    r["repo_id"]
                ))
                success_count += 1
            except Exception as e:
                logger.error(f"DB update failed for repo {r['repo_id']}: {e}")
                fail_count += 1
        else:
            fail_count += 1

    conn.commit()
    conn.close()
    return success_count, fail_count


async def main():
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("开始批量LLM审核 - DeepSeek v4-pro")
    logger.info("模式: 审核+分类，标记pending_api")
    logger.info("=" * 60)

    # 读取未标注记录
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, description, domain_tags, stars
        FROM rosclaw_hub_resources
        WHERE llm_analyzed_at IS NULL
    """)
    rows = cursor.fetchall()
    conn.close()

    total = len(rows)
    logger.info(f"待审核仓库数: {total}")

    if total == 0:
        logger.info("没有需要审核的仓库")
        return

    # 创建并发任务
    async with aiohttp.ClientSession() as session:
        tasks = []
        for row in rows:
            repo_id, name, description, domain_tags, stars = row
            task = analyze_repo(session, repo_id, name, description, domain_tags, stars)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

    # 处理异常结果
    processed_results = []
    for r in results:
        if isinstance(r, Exception):
            processed_results.append({"repo_id": -1, "success": False, "error": str(r)})
        else:
            processed_results.append(r)

    # 更新数据库
    success_count, fail_count = update_database(processed_results)

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info(f"审核完成!")
    logger.info(f"总仓库数: {total}")
    logger.info(f"成功: {success_count}")
    logger.info(f"失败: {fail_count}")
    logger.info(f"耗时: {elapsed:.1f}s ({elapsed/60:.1f}min)")
    logger.info(f"平均: {elapsed/max(total,1):.1f}s/仓库")
    logger.info("=" * 60)

    # 验证
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM rosclaw_hub_resources WHERE llm_analyzed_at IS NULL")
    remaining = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM rosclaw_hub_resources WHERE llm_upload_status = 'pending_api'")
    pending_api = cursor.fetchone()[0]
    conn.close()
    logger.info(f"剩余未标注: {remaining}")
    logger.info(f"pending_api总数: {pending_api}")


if __name__ == "__main__":
    asyncio.run(main())
