import json

import boto3

from open_brain.config import settings

_client = None

EXTRACTION_PROMPT = """Analyze this thought/note and extract structured metadata. Return ONLY valid JSON with these fields:

{
  "people": ["names of people mentioned"],
  "topics": ["1-3 topic tags"],
  "action_items": ["any tasks or action items"],
  "type": "observation|task|idea|reference|person_note",
  "summary": "one sentence summary"
}

If a field has no relevant data, use an empty array [] or appropriate default.

Thought to analyze:
"""


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=settings.aws_bedrock_region)
    return _client


async def extract_metadata(content: str) -> dict:
    """Extract structured metadata from thought content using Claude Haiku."""
    client = _get_client()

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 512,
        "messages": [
            {
                "role": "user",
                "content": EXTRACTION_PROMPT + content,
            }
        ],
    })

    response = client.invoke_model(
        modelId=settings.metadata_model,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]

    # Parse JSON from response, handling potential markdown code blocks
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return {
            "people": [],
            "topics": [],
            "action_items": [],
            "type": "observation",
            "summary": content[:100],
        }
