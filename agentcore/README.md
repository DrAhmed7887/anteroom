# Amazon Bedrock AgentCore Architecture

Anteroom exposes its core autonomous multi-agent coordination capabilities to **Amazon Bedrock AgentCore** as a native Action Group backed by serverless AWS Lambda and OpenAPI 3.0.

---

## 1. Action Group Endpoints

The Action Group defines three deterministic clinical operations in [`openapi.json`](file:///Users/ahmedzayed/Downloads/Agents%20for%20Humans%20Hackathon/anteroom/agentcore/openapi.json):

| Path | Method | Operation ID | Description |
|---|---|---|---|
| `/audit` | `POST` | `auditIntakePacket` | Deterministically audits an intake packet against specialty visit requirements. Evaluates readiness score (0–100), flags blocking gaps, and routes follow-up phone scripts to reception, nurse, or doctor. |
| `/brief` | `GET` | `getClinicianBrief` | Synthesizes an evidence-backed pre-visit narrative for clinicians, highlighting key facts with exact bounding box citations. |
| `/reconcile` | `POST` | `reconcileMedications` | Cross-document reconciliation detecting altered or unverified high-risk drugs across transitions of care. |

---

## 2. Directory Structure

```
agentcore/
├── agent_definition.json    # Bedrock Agent configuration (Claude 3.5 Sonnet v2)
├── openapi.json             # OpenAPI 3.0.0 Action Group schema
├── handler.py               # Lambda entry point bridging Bedrock events to Anteroom
├── trust_policy.json        # IAM assume-role trust policy for bedrock.amazonaws.com
├── iam_policy.json          # IAM permissions for Bedrock model invocation & Lambda
├── deploy.py                # Automated packaging and provisioning script
└── dist/                    # Packaged Lambda distribution bundles (.zip)
```

---

## 3. Local Verification & Packaging

Run the automated validator, test runner, and packager:

```bash
uv run python agentcore/deploy.py
```

This will:
1. Validate `openapi.json` against OpenAPI 3.0 specification.
2. Verify `agent_definition.json` foundation model mappings.
3. Test `handler.py` locally against synthetic Bedrock action group events.
4. Package `agentcore/dist/anteroom_action_group.zip` containing all dependencies.

---

## 4. Live Bedrock Provisioning

To provision directly into Amazon Bedrock:

```bash
# 1. Create execution role (one-time setup by AWS administrator)
aws iam create-role --role-name AnteroomBedrockRole \
  --assume-role-policy-document file://agentcore/trust_policy.json

aws iam put-role-policy --role-name AnteroomBedrockRole \
  --policy-name BedrockInvoke \
  --policy-document file://agentcore/iam_policy.json

# 2. Deploy and prepare Bedrock Agent
uv run python agentcore/deploy.py --apply --role-arn arn:aws:iam::<ACCOUNT_ID>:role/AnteroomBedrockRole
```
