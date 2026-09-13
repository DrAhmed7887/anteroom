"""Automated deployment script for Amazon Bedrock AgentCore.

Validates OpenAPI 3.0 schemas, packages the Action Group Lambda function,
and provisions/updates the Amazon Bedrock Agent.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import boto3
from botocore.exceptions import ClientError

from agentcore.handler import lambda_handler

AGENTCORE_DIR = Path(__file__).resolve().parent
OPENAPI_FILE = AGENTCORE_DIR / "openapi.json"
AGENT_DEF_FILE = AGENTCORE_DIR / "agent_definition.json"
DIST_DIR = AGENTCORE_DIR / "dist"
PACKAGE_ZIP = DIST_DIR / "anteroom_action_group.zip"


def validate_schemas() -> tuple[dict, dict]:
    print(" [1/4] Validating OpenAPI and Agent definition schemas...")
    if not OPENAPI_FILE.exists():
        raise FileNotFoundError(f"Missing {OPENAPI_FILE}")
    if not AGENT_DEF_FILE.exists():
        raise FileNotFoundError(f"Missing {AGENT_DEF_FILE}")

    openapi_spec = json.loads(OPENAPI_FILE.read_text())
    agent_def = json.loads(AGENT_DEF_FILE.read_text())

    assert openapi_spec.get("openapi", "").startswith("3.0"), "OpenAPI spec must be version 3.0.x"
    assert "paths" in openapi_spec, "OpenAPI spec must define paths"
    assert "/audit" in openapi_spec["paths"], "Must define /audit"
    assert "/brief" in openapi_spec["paths"], "Must define /brief"
    assert "/reconcile" in openapi_spec["paths"], "Must define /reconcile"

    print(f"       ✅ OpenAPI spec valid ({len(openapi_spec['paths'])} endpoints: {', '.join(openapi_spec['paths'].keys())})")
    print(f"       ✅ Agent definition valid (Model: {agent_def['foundationModel']})")
    return openapi_spec, agent_def


def test_handler_locally():
    print(" [2/4] Testing Action Group handler with local synthetic events...")
    test_event = {
        "messageVersion": "1.0",
        "actionGroup": "IntakeCoordinatorActions",
        "apiPath": "/audit",
        "httpMethod": "POST",
        "requestBody": {
            "content": {
                "application/json": {
                    "properties": [
                        {"name": "appointment_id", "value": "apt-001"}
                    ]
                }
            }
        }
    }
    resp = lambda_handler(test_event)
    assert resp["response"]["httpStatusCode"] == 200, f"Expected 200, got {resp}"
    body = json.loads(resp["response"]["responseBody"]["application/json"]["body"])
    # Assert the property, not a pinned literal. The handler's job is to report
    # what the pipeline computed; pinning a number makes every legitimate recall
    # improvement fail as though it were a regression.
    from anteroom.store import STORE_DIR
    cached = json.loads((STORE_DIR / "apt-001.json").read_text())
    assert body["score"] == cached["report"]["score"], (
        f"Handler score {body.get('score')} disagrees with the cached pipeline "
        f"result {cached['report']['score']}"
    )
    assert body["status"] == cached["report"]["status"]
    print(f"       ✅ Handler executed successfully: Patient {body['patient_ref']}, Score {body['score']}/100, Status {body['status']}")


def package_lambda():
    print(" [3/4] Packaging Lambda deployment bundle...")
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if PACKAGE_ZIP.exists():
        PACKAGE_ZIP.unlink()

    with zipfile.ZipFile(PACKAGE_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        # Include agentcore code
        zf.write(AGENTCORE_DIR / "handler.py", "handler.py")
        zf.write(AGENTCORE_DIR / "openapi.json", "openapi.json")

        # Include anteroom package
        anteroom_pkg = REPO_ROOT / "anteroom"
        for py_file in anteroom_pkg.rglob("*.py"):
            rel = py_file.relative_to(REPO_ROOT)
            zf.write(py_file, str(rel))

        # Include config
        config_dir = REPO_ROOT / "config"
        for cfg in config_dir.rglob("*.yaml"):
            rel = cfg.relative_to(REPO_ROOT)
            zf.write(cfg, str(rel))

        # Include demo store data
        store_dir = REPO_ROOT / "data" / "store"
        for f in store_dir.glob("*.json"):
            rel = f.relative_to(REPO_ROOT)
            zf.write(f, str(rel))

    size_kb = PACKAGE_ZIP.stat().st_size / 1024
    print(f"       ✅ Artifact created: {PACKAGE_ZIP.relative_to(REPO_ROOT)} ({size_kb:.1f} KB)")


def deploy_bedrock_agent(role_arn: str | None, region: str = "us-east-1"):
    print(" [4/4] Bedrock Agent provisioning...")
    client = boto3.client("bedrock-agent", region_name=region)
    _, agent_def = validate_schemas()

    if not role_arn:
        print("\n" + "=" * 60)
        print("  BEDROCK AGENT READY FOR PROVISIONING")
        print("=" * 60)
        print("  Action Group Lambda artifact: agentcore/dist/anteroom_action_group.zip")
        print("  OpenAPI Action Group schema  : agentcore/openapi.json")
        print("  Target Foundation Model      : " + agent_def["foundationModel"])
        print("\n  To attach an IAM role and provision live to Amazon Bedrock:")
        print(f"    uv run python agentcore/deploy.py --apply --role-arn <ROLE_ARN>")
        print("\n  Need to create the role first? Run:")
        print("    aws iam create-role --role-name AnteroomBedrockRole \\")
        print("      --assume-role-policy-document file://agentcore/trust_policy.json")
        print("    aws iam put-role-policy --role-name AnteroomBedrockRole \\")
        print("      --policy-name BedrockInvoke --policy-document file://agentcore/iam_policy.json")
        print("=" * 60 + "\n")
        return

    # Check if agent already exists
    agents = client.list_agents(maxResults=50).get("agentSummaries", [])
    existing = next((a for a in agents if a["agentName"] == agent_def["agentName"]), None)

    if existing:
        agent_id = existing["agentId"]
        print(f"  Updating existing Bedrock Agent {agent_def['agentName']} (ID: {agent_id})...")
        client.update_agent(
            agentId=agent_id,
            agentName=agent_def["agentName"],
            agentResourceRoleArn=role_arn,
            foundationModel=agent_def["foundationModel"],
            instruction=agent_def["instruction"],
        )
    else:
        print(f"  Creating new Bedrock Agent {agent_def['agentName']}...")
        resp = client.create_agent(
            agentName=agent_def["agentName"],
            agentResourceRoleArn=role_arn,
            foundationModel=agent_def["foundationModel"],
            instruction=agent_def["instruction"],
            description="Ambient pre-visit clinical intake coordinator built for AWS Agents Hackathon",
        )
        agent_id = resp["agent"]["agentId"]
        print(f"  Created agent ID: {agent_id}")

    # Prepare agent
    prep = client.prepare_agent(agentId=agent_id)
    print(f"  Agent prepared. Status: {prep.get('agentStatus', 'PREPARING')}")
    print(f"  🎉 Amazon Bedrock AgentCore deployment complete for {agent_def['agentName']} (ID: {agent_id})")


def main():
    parser = argparse.ArgumentParser(description="Anteroom Bedrock AgentCore Deployment")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Run validation and local packaging only")
    parser.add_argument("--apply", action="store_true", default=False, help="Deploy agent to Amazon Bedrock")
    parser.add_argument("--role-arn", type=str, default=None, help="IAM Role ARN for Bedrock execution")
    parser.add_argument("--region", type=str, default="us-east-1", help="AWS Region (default: us-east-1)")
    args = parser.parse_args()

    print("\n=======================================================")
    print("  ANTEROOM BEDROCK AGENTCORE PACKAGING & DEPLOYMENT")
    print("=======================================================\n")

    validate_schemas()
    test_handler_locally()
    package_lambda()
    deploy_bedrock_agent(role_arn=args.role_arn, region=args.region)


if __name__ == "__main__":
    main()
