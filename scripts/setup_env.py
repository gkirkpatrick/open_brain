#!/usr/bin/env python3
"""Generate .env file from AWS Secrets Manager and Superschedules config."""
import json
import os
import subprocess
import sys


def main():
    # Get secrets from AWS
    result = subprocess.run(
        ["aws", "secretsmanager", "get-secret-value",
         "--secret-id", "prod/superschedules/secrets",
         "--region", "us-east-1",
         "--query", "SecretString",
         "--output", "text"],
        capture_output=True, text=True, check=True,
    )
    secrets = json.loads(result.stdout.strip())

    # Read DB host from superschedules .env
    db_host = ""
    db_user = "superschedules"
    ss_env = "/opt/superschedules/.env"
    if os.path.exists(ss_env):
        with open(ss_env) as f:
            for line in f:
                if line.startswith("DB_HOST="):
                    db_host = line.split("=", 1)[1].strip().strip("'\"")
                elif line.startswith("DB_USER="):
                    db_user = line.split("=", 1)[1].strip().strip("'\"")

    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

    with open(env_path, "w") as f:
        f.write(f"DB_HOST={db_host}\n")
        f.write(f"DB_PORT=5432\n")
        f.write(f"DB_NAME=open_brain\n")
        f.write(f"DB_USER={db_user}\n")
        f.write(f"DB_PASSWORD={secrets['DB_PASSWORD']}\n")
        f.write(f"AWS_REGION=us-east-1\n")
        f.write(f"AWS_BEDROCK_REGION=us-east-1\n")
        f.write(f"EMBEDDING_MODEL=amazon.titan-embed-text-v2:0\n")
        f.write(f"EMBEDDING_DIMENSIONS=1024\n")
        f.write(f"METADATA_MODEL=anthropic.claude-3-haiku-20240307-v1:0\n")
        f.write(f"OPEN_BRAIN_ACCESS_KEY={secrets.get('OPEN_BRAIN_ACCESS_KEY', '')}\n")

    os.chmod(env_path, 0o600)
    print(f"Wrote {env_path}")


if __name__ == "__main__":
    main()
