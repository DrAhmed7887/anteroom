"""Tests for Amazon Bedrock AgentCore action group Lambda handler."""

import json

from anteroom.store import STORE_DIR
from agentcore.handler import lambda_handler


def test_agentcore_audit_action():
    event = {
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
    resp = lambda_handler(event)
    assert resp["messageVersion"] == "1.0"
    assert resp["response"]["httpStatusCode"] == 200
    body = json.loads(resp["response"]["responseBody"]["application/json"]["body"])
    assert body["patient_ref"] == "SYN-0001"
    assert body["status"] == "at_risk"
    assert body["blocking_gaps"] == 2
    # Assert the property, not a magic number. The score is deterministic for a
    # given pipeline, but pinning the literal makes every legitimate recall
    # improvement look like a regression -- which is what happened when the
    # deterministic evidence scanner closed two gaps and moved it from 32 to 40.
    cached = json.loads((STORE_DIR / "apt-001.json").read_text())
    assert body["score"] == cached["report"]["score"]
    assert 0 <= body["score"] <= 100


def test_agentcore_brief_action():
    event = {
        "messageVersion": "1.0",
        "actionGroup": "IntakeCoordinatorActions",
        "apiPath": "/brief",
        "httpMethod": "GET",
        "parameters": [
            {"name": "appointment_id", "type": "string", "value": "apt-001"}
        ]
    }
    resp = lambda_handler(event)
    assert resp["response"]["httpStatusCode"] == 200
    body = json.loads(resp["response"]["responseBody"]["application/json"]["body"])
    assert body["patient_ref"] == "SYN-0001"
    assert "palpitations" in body["headline"].lower()
    assert len(body["medications"]) > 0


def test_agentcore_reconcile_action():
    event = {
        "messageVersion": "1.0",
        "actionGroup": "IntakeCoordinatorActions",
        "apiPath": "/reconcile",
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
    resp = lambda_handler(event)
    assert resp["response"]["httpStatusCode"] == 200
    body = json.loads(resp["response"]["responseBody"]["application/json"]["body"])
    assert body["is_at_risk"] is True
    assert any(flag["medication"] == "Apixaban" for flag in body["reconciliation_flags"])


def test_agentcore_unknown_path():
    event = {
        "messageVersion": "1.0",
        "actionGroup": "IntakeCoordinatorActions",
        "apiPath": "/nonexistent",
        "httpMethod": "POST",
    }
    resp = lambda_handler(event)
    assert resp["response"]["httpStatusCode"] == 404
