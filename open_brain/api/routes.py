import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from open_brain.api.auth import verify_access_key
from open_brain.db.session import get_pool
from open_brain.services.embeddings import generate_embedding
from open_brain.services.metadata import extract_metadata

router = APIRouter(prefix="/api", dependencies=[Depends(verify_access_key)])


def _parse_meta(val):
    """Parse metadata from DB — may be dict or JSON string."""
    if isinstance(val, str):
        return json.loads(val)
    return val or {}


class ThoughtCreate(BaseModel):
    content: str
    source: str = "api"


class ThoughtResponse(BaseModel):
    id: str
    content: str
    source: str
    metadata: dict
    created_at: datetime


class StatsResponse(BaseModel):
    total_thoughts: int
    types: dict
    top_topics: list[dict]
    top_people: list[dict]


@router.post("/thoughts", response_model=ThoughtResponse)
async def create_thought(body: ThoughtCreate):
    """Capture a new thought with auto-generated embedding and metadata."""
    embedding, metadata = await asyncio.gather(
        generate_embedding(body.content),
        extract_metadata(body.content),
    )

    metadata["source"] = body.source
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
        body.content,
        embedding_str,
        body.source,
        json.dumps(metadata),
        now,
    )

    return ThoughtResponse(
        id=str(thought_id),
        content=body.content,
        source=body.source,
        metadata=metadata,
        created_at=now,
    )


@router.get("/thoughts")
async def list_thoughts(
    q: str | None = Query(None, description="Semantic search query"),
    limit: int = Query(10, ge=1, le=100),
    type: str | None = Query(None, description="Filter by thought type"),
    topic: str | None = Query(None, description="Filter by topic"),
    person: str | None = Query(None, description="Filter by person mentioned"),
    days: int | None = Query(None, description="Only thoughts from last N days"),
):
    """List or search thoughts."""
    pool = await get_pool()

    if q:
        # Semantic search
        embedding = await generate_embedding(q)
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        rows = await pool.fetch(
            """
            SELECT id, content, metadata, created_at,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM thoughts
            WHERE 1 - (embedding <=> $1::vector) > 0.3
            ORDER BY embedding <=> $1::vector
            LIMIT $2
            """,
            embedding_str,
            limit,
        )
        return [
            {
                "id": str(r["id"]),
                "content": r["content"],
                "metadata": _parse_meta(r["metadata"]),
                "similarity": round(float(r["similarity"]), 4),
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]

    # List with filters
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

    return [
        {
            "id": str(r["id"]),
            "content": r["content"],
            "source": r["source"],
            "metadata": _parse_meta(r["metadata"]),
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


@router.get("/thoughts/stats", response_model=StatsResponse)
async def thought_stats():
    """Get aggregated thought statistics."""
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
        LIMIT 20
        """
    )

    people_rows = await pool.fetch(
        """
        SELECT person, COUNT(*) AS count
        FROM thoughts, jsonb_array_elements_text(metadata->'people') AS person
        GROUP BY person
        ORDER BY count DESC
        LIMIT 20
        """
    )

    return StatsResponse(
        total_thoughts=total,
        types={r["type"]: r["count"] for r in type_rows},
        top_topics=[{"name": r["topic"], "count": r["count"]} for r in topic_rows],
        top_people=[{"name": r["person"], "count": r["count"]} for r in people_rows],
    )
