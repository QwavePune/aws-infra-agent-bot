# Maker-Checker IAM And Runtime Behavior

This document describes the implemented maker-checker model in the AGUI runtime.

## What The Feature Is

The maker-checker flow is enforced in `bin/agui_server.py` before selected mutating MCP tools execute.

The queue stores:

- tool name
- tool arguments
- requester profile
- target checker profile
- request status
- plan preview / execution result
- comment thread

The key design choice is that approval preserves the exact queued tool invocation. The checker does not ask the LLM to regenerate the change.

## Why This Exists

The project mixes conversational intent with real AWS side effects. The maker-checker gate exists to keep that operationally defensible:

- a maker can request a change without being able to execute it directly
- a checker can review the exact requested tool and arguments
- execution happens under the checker profile
- the workflow is visible in both the main console and the audit trail

## Profile Model

Checker and maker profiles are configured in:

- `logs/maker_checker_roles.json`

Default behavior:

- checker profiles come from `MAKER_CHECKER_CHECKER_PROFILES`, `MAKER_CHECKER_CHECKER_PROFILE`, or fall back to the current `AWS_PROFILE`
- maker profiles can be explicitly configured; if they are not, any non-checker profile is effectively treated as a maker for gating purposes

The browser uses a client-scoped profile context, so different clients can hold different active profiles at the same time within a single server process.

## Runtime Sequence

1. A user requests a mutating action.
2. The AGUI runtime evaluates `_maker_checker_should_gate(...)`.
3. If gating applies, the request is stored as `pending` and the UI receives maker-checker SSE updates.
4. A checker reviews the request, adds comments if needed, then approves or rejects it.
5. The checker executes the approved item through `/api/maker-checker/execute`.
6. The backend runs the queued tool with the stored arguments and records the result.

## Important Nuances

### This Is An Application-Level Control

Maker-checker is implemented in the AGUI backend, not in AWS IAM itself. IAM still matters because the actual execution ultimately depends on the effective AWS credentials of the checker profile.

### The Queue Is In-Memory

Queued requests live in process memory. The role configuration is persisted, but the request queue itself is not durable across process restarts.

### Approval Is Not The Same As Execution

The UI and API separate approval from execution:

- approve/reject changes status
- execute runs the exact approved action

This is useful because approval may happen before the operator is ready to incur the real infrastructure side effect.

### Audit Integration

Maker-checker events are merged into the audit trail built from workflow logs. That gives a single operator-facing timeline, even though the queue itself is not stored in the same JSONL format.

## Suggested IAM Shape

The repository includes policy JSON files under `deployment/json-files/` to support a maker/checker split:

- [maker-checker-maker-policy.json](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/deployment/json-files/maker-checker-maker-policy.json)
- [maker-checker-checker-policy.json](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/deployment/json-files/maker-checker-checker-policy.json)

The intended pattern is:

- maker: discovery and request submission
- checker: approval plus execution authority

## Relevant Endpoints

- `GET /api/maker-checker/config`
- `GET /api/maker-checker/roles`
- `POST /api/maker-checker/roles`
- `GET /api/maker-checker/requests`
- `GET /api/maker-checker/request/{request_id}`
- `POST /api/maker-checker/comment`
- `POST /api/maker-checker/approve`
- `POST /api/maker-checker/reject`
- `POST /api/maker-checker/execute`
