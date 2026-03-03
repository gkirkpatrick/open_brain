import json

import boto3

from open_brain.config import settings

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=settings.aws_bedrock_region)
    return _client


async def generate_embedding(text: str) -> list[float]:
    """Generate a vector embedding using AWS Bedrock Titan Embeddings v2."""
    client = _get_client()

    body = json.dumps({
        "inputText": text,
        "dimensions": settings.embedding_dimensions,
    })

    response = client.invoke_model(
        modelId=settings.embedding_model,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    result = json.loads(response["body"].read())
    return result["embedding"]
