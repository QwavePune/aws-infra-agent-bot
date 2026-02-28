# Maker-Checker IAM Design

This setup creates two IAM users for controlled MCP-driven infrastructure changes:

- `infra-maker`: can discover resources and submit requests, but cannot mutate infrastructure directly.
- `infra-checker`: can approve and execute queued requests via the AGUI maker-checker workflow.

The AGUI server treats `PKProtonProfile` as the default checker profile.

## Suggested Users

1. `infra-maker`
2. `infra-checker`

## Policies

- Maker policy file:
  - `/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/deployment/json-files/maker-checker-maker-policy.json`
- Checker policy file:
  - `/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/deployment/json-files/maker-checker-checker-policy.json`

## Attach Policies

Use customer-managed policies and attach:

1. Attach maker policy to `infra-maker`.
2. Attach checker policy to `infra-checker`.

## CLI Profiles

Define local profiles in `~/.aws/config` and `~/.aws/credentials` (or SSO profiles):

1. `infra-maker`
2. `PKProtonProfile` (checker)

AGUI defaults to `PKProtonProfile` if `AWS_PROFILE` is not set.

## Runtime Behavior

- If current profile is not checker (`PKProtonProfile`) and a mutating MCP tool is requested:
  - request is queued as `pending`
  - checker must approve/reject from maker-checker queue panel
- Checker approval executes the exact queued tool + args using checker profile.

## API Endpoints

- `GET /api/maker-checker/config`
- `GET /api/maker-checker/requests?status=pending`
- `POST /api/maker-checker/approve`
- `POST /api/maker-checker/reject`
