# CI/CD Pipeline Demo — Setup Guide

## Infrastructure required

| Component | Purpose | How to provision |
|-----------|---------|------------------|
| AAP 2.7+ with automation orchestrator | Job templates + workflow engine | Existing AAP / containerized install |
| Demo VM (RHEL 9) | Runs inventory-service on ports 80 (prod) and 8080 (dev); optional Gitea host | EC2 t3.medium or similar |
| Gitea + Actions runner | App repo, PR merge, CI webhook to AO | `setup/cicd_setup_gitea.yml` on the demo VM |
| OpenFlake | Change request work notes and close (ServiceNow-compatible Table API) | Lab OpenFlake instance; `/api/now` is rewritten to `/api/flake` |
| AI credential | Three Task agents that write ITSM close/failure notes | Any supported model in AO |

One Linux host can run both the app (dev+prod) and Gitea for a compact lab.

## Architecture

```text
Gitea PR merge → CI (pytest) → AO webhook /lightwell-ci-cd
  → Deploy Dev + Test → Condition
       ├── false → AI failure note (halt)
       └── true  → Approval → Drain LB → Deploy Prod + Smoke → Condition
                      ├── true  → AI close note → Close CHG
                      └── false → AI rollback note → Rollback snapshot
```

## Step-by-step setup

### 1. Provision the demo host

```bash
# Inventory example
# [cicd_demo]
# cicd-demo-vm ansible_host=<IP> ansible_user=ec2-user
```

Run the setup playbooks against that host:

```bash
ansible-playbook -i inventory cicd-pipeline/setup/cicd_setup_demo_host.yml
ansible-playbook -i inventory cicd-pipeline/setup/cicd_setup_gitea.yml \
  -e gitea_admin_password='<strong-password>'
```

Save the Gitea API token printed by the Gitea setup playbook.

### 2. Create the inventory-service repo in Gitea

Create a repo named `inventory-service` under the admin user with at least:

- `requirements.txt` pinned to `aiohttp==3.9.0`
- `version.txt` at `2.3.0`
- empty `PATCHED_CVE` and `CHANGE_REQUEST` files
- A Gitea Actions workflow that runs pytest and, on success, POSTs to the AO webhook with:

```json
{
  "app_name": "inventory-service",
  "artifact_version": "<version>-b<run>",
  "git_sha": "<sha>",
  "ci_build_url": "<actions run url>",
  "affected_cve": "<from PATCHED_CVE>",
  "change_request": "<from CHANGE_REQUEST>",
  "ci_build_number": "<run number>"
}
```

CI should exit early (no AO webhook) when `CHANGE_REQUEST` is empty — that is what **Reset Demo** relies on.

### 3. Configure AAP project and inventory

1. **Project** — sync this repository (or the `cicd-pipeline/` subtree).
2. **Inventory** — one host for the demo VM (SSH machine credential).
3. **Credentials / extra vars** for OpenFlake and Gitea:

Playbooks talk to **OpenFlake** over its ServiceNow-compatible Table API (`/api/flake/table/...`). They accept either OpenFlake vars/env or the product-demos `SN_*` ServiceNow credential env names.

| Variable / env | Purpose |
|----------------|---------|
| `openflake_instance_url` or `OPENFLAKE_INSTANCE_URL` or `SN_HOST` | OpenFlake base URL (no trailing slash) |
| `openflake_username` / `OPENFLAKE_USERNAME` / `SN_USERNAME` | Basic-auth user (default `admin`) |
| `openflake_password` / `OPENFLAKE_PASSWORD` / `SN_PASSWORD` | Basic-auth password |
| `itsm_api_prefix` | API prefix (default `/api/flake`; set `/api/now` only if you rely on OpenFlake’s rewrite) |
| `openflake_validate_certs` | TLS verify for OpenFlake calls (default `true`) |
| `gitea_host` / `gitea_port` | Gitea endpoint (defaults: `gitea.example.local:3000`) |
| `gitea_token` | Admin API token from setup |
| `gitea_owner` / `gitea_repo` | Defaults: `gitea-admin` / `inventory-service` |

Shared helpers live in `playbooks/tasks/openflake_*.yml`. OpenFlake **replaces** `work_notes` on PATCH (it does not journal-append like ServiceNow), so those tasks append to the existing note text before writing.

### 4. Register job templates

| Name | Playbook | Limit / runs on |
|------|----------|-----------------|
| CI/CD Demo - Deploy and Test Dev | `playbooks/cicd_deploy_dev_and_test.yml` | Demo host |
| CI/CD Demo - Drain Load Balancer | `playbooks/cicd_drain_lb.yml` | Demo host |
| CI/CD Demo - Deploy to Prod | `playbooks/cicd_deploy_prod.yml` | Demo host |
| CI/CD Demo - Rollback to Snapshot | `playbooks/cicd_rollback_to_snapshot.yml` | Demo host |
| CI/CD Demo - Close Loop | `playbooks/cicd_close_loop.yml` | localhost |
| CI/CD Demo - Simulate Lightwell PR | `playbooks/cicd_simulate_lightwell_pr.yml` | localhost |
| CI/CD Demo - Reset Demo | `playbooks/cicd_reset_demo.yml` | Demo host |

Enable **Prompt on launch → Extra Variables** on templates that receive AO expressions (`app_name`, `artifact_version`, `change_request`, `ao_*` artifacts, AI note fields).

Optional one-time templates for setup:

| Name | Playbook |
|------|----------|
| CI/CD Demo - Setup Demo Host | `setup/cicd_setup_demo_host.yml` |
| CI/CD Demo - Setup Gitea | `setup/cicd_setup_gitea.yml` |

### 5. Import the automation orchestrator workflow

1. Import [`ao/cicd-pipeline.json`](ao/cicd-pipeline.json).
2. Bind your AAP integration / credential on each AAP job step (names must match the table above).
3. Attach an AI credential/model on the three Task agent steps.
4. Note the webhook path: **`lightwell-ci-cd`**. Authorize the CI service account to call it.
5. Point the Gitea Actions success step at the AO webhook URL for that path.

### 6. Configure AI agents

The agents only write prose for ServiceNow — no MCP tools required (`tool_selection_strategy: NONE`). Any supported LLM credential works.

## Demo runbook

Before every recording or live show:

1. Run **CI/CD Demo - Reset Demo** (reverts Gitea to vulnerable `aiohttp==3.9.0`).
2. Run **CI/CD Demo - Simulate Lightwell PR** — creates a SNOW change and opens the Lightwell PR (~30s).
3. Open the CHG in OpenFlake and the AO canvas side by side.
4. Merge the PR in Gitea live — that is the trigger moment.
5. Switch to the AO canvas; hold at approval and read the prompt aloud.
6. Approve; watch LB drain → prod deploy → AI close note → CHG Closed.

**Rollback path (separate take):** break the prod `/health` endpoint before the run so the smoke-test condition takes the false branch.

## Webhook payload reference

| Field | Example |
|-------|---------|
| `app_name` | `inventory-service` |
| `artifact_version` | `2.4.0-b20` |
| `git_sha` | commit SHA from CI |
| `ci_build_url` | Gitea Actions run URL |
| `ci_build_number` | run number |
| `affected_cve` | `CVE-2024-23334` |
| `change_request` | `CHG0034861` |

## Key artifacts published by playbooks

| Artifact | Source | Consumed by |
|----------|--------|-------------|
| `ao_dev_test_passed` | Deploy Dev | Dev Tests Passed? condition |
| `ao_dev_test_summary` | Deploy Dev | AI failure note agent |
| `ao_prod_health_passed` | Deploy Prod | Prod Smoke Test Passed? condition |
| `ao_smoke_test_summary` | Deploy Prod | AI success / rollback agents |
| `ao_snapshot_id` | Deploy Prod | Rollback job |
| `ao_failed_checks` | Deploy Prod | AI rollback agent |
