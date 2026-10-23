# Check Mode Change Control - Requirements

## Infrastructure

| Component | Required | Notes |
|-----------|----------|-------|
| Ansible Automation Platform | Yes | 2.7+ with automation orchestrator |
| ServiceNow instance | Yes | Change request access + credentials for the REST API |
| Multi-domain inventory | Yes | At least 3 RHEL hosts across inventory groups `web`, `db`, `loadbalancer` |

No MCP server is required — all ServiceNow interactions go through AAP job templates using the REST API, and the AI agents only scan job artifacts.

## Hosts

Domains are inventory groups: every group a host belongs to gets its own task block, and impact is reported per host per domain. **One VM is enough** — make it a member of all three demo groups:

| Option | Inventory setup | Impact report shows |
|--------|-----------------|---------------------|
| Single VM (minimum) | web1 in groups `web`, `db`, `loadbalancer` | One host across three domains |
| Three VMs (full picture) | web1 in `web`, db1 in `db`, lb1 in `loadbalancer` | One host per domain |

Add hosts to new groups to extend the report — the playbook needs no changes.

## AAP Setup

1. Project: `Change-Control-Playbooks` pointing to this repository (or a copy of `check-mode-change-control/aap/playbooks/`)
2. Job template: `Multi-Domain Change - Check` using `multi_domain_change.yml`, **job_type: check**, prompt-on-launch enabled for Variables
3. Job template: `Multi-Domain Change - Apply` using `multi_domain_change.yml`, **job_type: run**, prompt-on-launch enabled for Variables
4. Job template: `Update SNOW Change` using `update_snow_change.yml`, runs on localhost
5. Job template: `Simulate - Change Process Initiation` using `test/simulate_change_process.yml`, runs on localhost
6. Target templates need the lab SSH credential attached; both localhost templates need ServiceNow credentials injected as environment variables

## Custom credential type: ServiceNow credentials

Both localhost job templates read ServiceNow credentials from the environment. Create an AAP custom credential type injecting these environment variables:

```yaml
# Injectors: env
SNOW_INSTANCE_URL: "{{ SNOW_INSTANCE_URL }}"
SNOW_USERNAME: "{{ SNOW_USERNAME }}"
SNOW_PASSWORD: "{{ SNOW_PASSWORD }}"
```

Attach the credential to `Update SNOW Change` and `Simulate - Change Process Initiation`.

## Credentials (placeholders in the workflow JSON)

Replace these before importing, or after import via the automation orchestrator UI:

| Placeholder | What it is |
|-------------|------------|
| `YOUR_AO_MODEL_CREDENTIAL_ID` | automation orchestrator model credential for the AI agents (tested with `claude-sonnet-4-6`) |
| `YOUR_AO_AAP_CREDENTIAL_ID` | automation orchestrator AAP integration credential used by all `aap_job_template` nodes |

## Simulation Environment Variables

The `Simulate - Change Process Initiation` job template additionally reads these from the environment (same custom credential type or a second one):

- `AO_BASE_URL`, `AO_CLIENT_ID`, `AO_CLIENT_SECRET` — automation orchestrator service account for token + webhook

## Webhook

The workflow triggers on POST `http://<AO_HOST>/api/v1/webhooks/change-request` with payload:

```json
{
  "number": "CHG0030001",
  "summary": "Short description of the change",
  "risk": "low"
}
```

`summary` and `risk` are optional — the simulation playbook sends them so the AI impact analyst has the change intent; without them the analyst works from the check-mode artifacts alone. The simulation playbook creates the change request and fires this webhook itself, so no manual curl is needed.

## Workflow Inputs

| Input | Type | Description |
|-------|------|-------------|
| `number` | string | ServiceNow change request number (e.g. CHG0030001) |
| `summary` | string | Optional — change short description for the AI analyst |
| `risk` | string | Optional — risk as filed on the change request |

## Extra Vars

| Extra var | Set by | Description |
|-----------|--------|-------------|
| `change_number` | automation orchestrator | Change request number, passed to both the change run and the SNOW update templates |
| `work_notes` | automation orchestrator | Work note body posted to ServiceNow by `Update SNOW Change` |
| `snow_state` | automation orchestrator | Optional target state for the change request (`3` = Closed on the approved path) |
| `baseline_package` | optional | Package the playbook ensures present (default `chrony`) |
