"""Amazon Bedrock AgentCore Action Group Lambda Handler.

Bridges Amazon Bedrock Agent runtimes to Anteroom's deterministic readiness
auditor, Strands agent coordinators, and cross-document reconciliation engine.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from anteroom.brief import compose as compose_brief
from anteroom.readiness import audit, load_policy
from anteroom.schemas import Confidence, IntakeRecord, ReadinessReport, Severity
from anteroom.store import STORE_DIR, load_appointments

logger = logging.getLogger("anteroom.agentcore")
logger.setLevel(logging.INFO)


def _parse_properties(body_dict: dict) -> dict[str, Any]:
    """Parse Bedrock's requestBody.content.application/json which can be a dict
    or a list of property objects [{"name": "k", "value": "v"}]."""
    if not body_dict:
        return {}
    content = body_dict.get("content", {})
    app_json = content.get("application/json", {})
    if isinstance(app_json, dict) and "properties" in app_json:
        props = app_json["properties"]
        if isinstance(props, list):
            return {item["name"]: item.get("value") for item in props if "name" in item}
        if isinstance(props, dict):
            return props
    if isinstance(app_json, dict):
        return app_json
    return {}


def _parse_params(param_list: list[dict] | None) -> dict[str, Any]:
    if not param_list:
        return {}
    return {p["name"]: p.get("value") for p in param_list if "name" in p}


def handle_audit(params: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    apt_id = body.get("appointment_id") or params.get("appointment_id")
    if apt_id:
        p = Path(STORE_DIR) / f"{apt_id}.json"
        if p.exists():
            data = json.loads(p.read_text())
            rep = data["report"]
            return {
                "patient_ref": rep["patient_ref"],
                "visit_type": rep["visit_type"],
                "status": rep["status"],
                "score": rep["score"],
                "total_gaps": len(rep["gaps"]),
                "blocking_gaps": len([g for g in rep["gaps"] if g["severity"] == "blocking"]),
                "gaps": [
                    {
                        "field": g["field"],
                        "severity": g["severity"],
                        "reason": g["reason"],
                        "owner": g["owner"],
                        "action": g["action"],
                        "call_script": g.get("call_script"),
                    }
                    for g in rep["gaps"]
                ],
            }

    # If raw record metadata provided
    patient_ref = body.get("patient_ref", "SYN-UNKNOWN")
    visit_type = body.get("visit_type", "cardiology_new_consult")
    apt_at_str = body.get("appointment_at")
    apt_at = datetime.fromisoformat(apt_at_str) if apt_at_str else datetime.now()

    record = IntakeRecord(patient_ref=patient_ref, appointment_at=apt_at, visit_type=visit_type)
    rep = audit(record)
    return {
        "patient_ref": rep.patient_ref,
        "visit_type": rep.visit_type,
        "status": rep.status.value,
        "score": rep.score,
        "total_gaps": len(rep.gaps),
        "blocking_gaps": len(rep.blocking_gaps),
        "gaps": [
            {
                "field": g.field,
                "severity": g.severity.value,
                "reason": g.reason,
                "owner": g.owner.value,
                "action": g.action,
                "call_script": g.call_script,
            }
            for g in rep.gaps
        ],
    }


def handle_brief(params: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    apt_id = params.get("appointment_id") or body.get("appointment_id", "apt-001")
    p = Path(STORE_DIR) / f"{apt_id}.json"
    if not p.exists():
        return {"error": f"Appointment {apt_id} not found."}

    data = json.loads(p.read_text())
    brief_data = data.get("brief", {})
    narrative = brief_data.get("narrative", {})
    return {
        "patient_ref": brief_data.get("patient_ref", "UNKNOWN"),
        "appointment": brief_data.get("appointment", ""),
        "headline": narrative.get("headline", ""),
        "medications": brief_data.get("medications", []),
        "not_documented": brief_data.get("not_documented", []),
        "flags": brief_data.get("flags", []),
    }


def handle_reconcile(params: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    apt_id = body.get("appointment_id") or params.get("appointment_id", "apt-001")
    p = Path(STORE_DIR) / f"{apt_id}.json"
    if not p.exists():
        return {"error": f"Appointment {apt_id} not found."}

    data = json.loads(p.read_text())
    rep = data.get("report", {})
    gaps = rep.get("gaps", [])

    reconciled_gaps = [g for g in gaps if g.get("field", "").startswith("unreconciled_change:")]
    return {
        "patient_ref": rep.get("patient_ref", "SYN-0001"),
        "reconciliation_flags": [
            {
                "medication": g["field"].split(":", 1)[1],
                "severity": g["severity"],
                "action": g["action"],
            }
            for g in reconciled_gaps
        ],
        "is_at_risk": any(g["severity"] == "blocking" for g in reconciled_gaps),
    }


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Bedrock Agent Action Group entry point."""
    logger.info("AgentCore Action Group invocation: %s", json.dumps(event))

    action_group = event.get("actionGroup", "IntakeCoordinatorActions")
    api_path = event.get("apiPath", "/audit")
    http_method = event.get("httpMethod", "POST").upper()

    params = _parse_params(event.get("parameters", []))
    body = _parse_properties(event.get("requestBody", {}))

    status_code = 200
    try:
        if api_path == "/audit":
            result = handle_audit(params, body)
        elif api_path == "/brief":
            result = handle_brief(params, body)
        elif api_path == "/reconcile":
            result = handle_reconcile(params, body)
        else:
            status_code = 404
            result = {"error": f"Unknown API path: {api_path}"}
    except Exception as exc:
        logger.exception("Error executing action %s %s: %s", http_method, api_path, exc)
        status_code = 500
        result = {"error": str(exc)}

    response_payload = {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "apiPath": api_path,
            "httpMethod": http_method,
            "httpStatusCode": status_code,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(result)
                }
            },
        },
    }
    return response_payload
