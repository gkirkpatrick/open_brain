import asyncio
import json
import uuid
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from open_brain.db.session import get_pool
from open_brain.services.embeddings import generate_embedding
from open_brain.services.metadata import extract_metadata

mcp = FastMCP("open-brain")


@mcp.tool()
async def search_thoughts(query: str, limit: int = 10, threshold: float = 0.3) -> str:
    """Search thoughts by semantic similarity. Returns thoughts ranked by relevance to your query."""
    embedding = await generate_embedding(query)
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, content, metadata, created_at,
               1 - (embedding <=> $1::vector) AS similarity
        FROM thoughts
        WHERE 1 - (embedding <=> $1::vector) > $2
        ORDER BY embedding <=> $1::vector
        LIMIT $3
        """,
        embedding_str,
        threshold,
        limit,
    )

    if not rows:
        return "No matching thoughts found."

    results = []
    for r in rows:
        meta = r["metadata"] or {}
        topics = meta.get("topics", [])
        result = f"[{r['created_at'].strftime('%Y-%m-%d')}] (similarity: {float(r['similarity']):.2f})"
        if topics:
            result += f" [{', '.join(topics)}]"
        result += f"\n{r['content']}"
        results.append(result)

    return f"Found {len(rows)} thoughts:\n\n" + "\n\n---\n\n".join(results)


@mcp.tool()
async def list_thoughts(
    limit: int = 10,
    type: str | None = None,
    topic: str | None = None,
    person: str | None = None,
    days: int | None = None,
) -> str:
    """Browse recent thoughts with optional filters by type, topic, person, or time range."""
    pool = await get_pool()

    conditions = []
    params = []
    param_idx = 1

    if type:
        conditions.append(f"metadata->>'type' = ${param_idx}")
        params.append(type)
        param_idx += 1

    if topic:
        conditions.append(f"metadata->'topics' ? ${param_idx}")
        params.append(topic)
        param_idx += 1

    if person:
        conditions.append(f"metadata->'people' ? ${param_idx}")
        params.append(person)
        param_idx += 1

    if days:
        conditions.append(f"created_at > NOW() - INTERVAL '{int(days)} days'")

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    params.append(limit)

    rows = await pool.fetch(
        f"""
        SELECT id, content, source, metadata, created_at
        FROM thoughts
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ${param_idx}
        """,
        *params,
    )

    if not rows:
        return "No thoughts found matching the filters."

    results = []
    for r in rows:
        meta = r["metadata"] or {}
        topics = meta.get("topics", [])
        thought_type = meta.get("type", "unknown")
        result = f"[{r['created_at'].strftime('%Y-%m-%d %H:%M')}] ({thought_type})"
        if topics:
            result += f" [{', '.join(topics)}]"
        result += f"\n{r['content']}"
        results.append(result)

    return f"Showing {len(rows)} thoughts:\n\n" + "\n\n---\n\n".join(results)


@mcp.tool()
async def thought_stats() -> str:
    """Get aggregated statistics about captured thoughts."""
    pool = await get_pool()

    total = await pool.fetchval("SELECT COUNT(*) FROM thoughts")

    type_rows = await pool.fetch(
        """
        SELECT metadata->>'type' AS type, COUNT(*) AS count
        FROM thoughts
        WHERE metadata->>'type' IS NOT NULL
        GROUP BY metadata->>'type'
        ORDER BY count DESC
        """
    )

    topic_rows = await pool.fetch(
        """
        SELECT topic, COUNT(*) AS count
        FROM thoughts, jsonb_array_elements_text(metadata->'topics') AS topic
        GROUP BY topic
        ORDER BY count DESC
        LIMIT 10
        """
    )

    people_rows = await pool.fetch(
        """
        SELECT person, COUNT(*) AS count
        FROM thoughts, jsonb_array_elements_text(metadata->'people') AS person
        GROUP BY person
        ORDER BY count DESC
        LIMIT 10
        """
    )

    lines = [f"Total thoughts: {total}\n"]

    if type_rows:
        lines.append("By type:")
        for r in type_rows:
            lines.append(f"  {r['type']}: {r['count']}")
        lines.append("")

    if topic_rows:
        lines.append("Top topics:")
        for r in topic_rows:
            lines.append(f"  {r['topic']}: {r['count']}")
        lines.append("")

    if people_rows:
        lines.append("Most mentioned people:")
        for r in people_rows:
            lines.append(f"  {r['person']}: {r['count']}")

    return "\n".join(lines)


@mcp.tool()
async def capture_thought(content: str) -> str:
    """Capture a new thought. Automatically generates embeddings and extracts metadata (topics, people, action items, type)."""
    embedding, metadata = await asyncio.gather(
        generate_embedding(content),
        extract_metadata(content),
    )

    metadata["source"] = "mcp"
    thought_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO thoughts (id, content, embedding, source, metadata, created_at, updated_at)
        VALUES ($1, $2, $3::vector, $4, $5::jsonb, $6, $6)
        """,
        thought_id,
        content,
        embedding_str,
        "mcp",
        json.dumps(metadata),
        now,
    )

    topics = metadata.get("topics", [])
    thought_type = metadata.get("type", "observation")
    action_items = metadata.get("action_items", [])
    summary = metadata.get("summary", "")

    lines = [f"Thought captured as {thought_type}."]
    if topics:
        lines.append(f"Topics: {', '.join(topics)}")
    if action_items:
        lines.append(f"Action items: {', '.join(action_items)}")
    if summary:
        lines.append(f"Summary: {summary}")

    return "\n".join(lines)
