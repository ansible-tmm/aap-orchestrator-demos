# Check Mode Change Control - Setup Guide

See the impact before you commit: run the multi-domain change in check mode, get an AI impact report on the change request, then approve or reject.

## What you need

| Component | Where |
|-----------|-------|
| AAP with automation orchestrator | Your lab AAP instance |
| ServiceNow instance | Developer instance or your own, with change_request access |
| 3 RHEL 9.x hosts | In AAP inventory groups `web`, `db`, `loadbalancer` |

No MCP server is needed — ServiceNow interactions go through job templates over the REST API.

## 1. AAP Setup

### Inventory

Domains are inventory groups, and **one VM is enough** — make it a member of all three groups. (With three VMs, put each in one group.)

| Host | Groups |
|------|--------|
| web1 | web, db, loadbalancer |

The playbook runs each group's task block on the host and reports impact per host per domain, so the single VM produces a full three-domain impact report. Group membership is the domain: the playbook reads each host's `group_names` to build the impact report.

### Project

Create a project `Change-Control-Playbooks` pointing at this repository (or a Gitea copy containing `check-mode-change-control/aap/playbooks/`).

### Custom credential type: ServiceNow credentials

Create an AAP custom credential type injecting these environment variables:

```yaml
# Injectors: env
SNOW_INSTANCE_URL: "{{ SNOW_INSTANCE_URL }}"
SNOW_USERNAME: "{{ SNOW_USERNAME }}"
SNOW_PASSWORD: "{{ SNOW_PASSWORD }}"
```

### Job Templates

#### Multi-Domain Change - Check

| Setting | Value |
|---------|-------|
| Playbook | `multi_domain_change.yml` |
| Job type | **Check** |
| Credential | Lab SSH credential |
| Prompt on launch | Variables (for `change_number`) |
| Privilege escalation | Yes |

#### Multi-Domain Change - Apply

Same as above, but **Job type: Run**.

#### Update SNOW Change

| Setting | Value |
|---------|-------|
| Playbook | `update_snow_change.yml` |
| Credential | ServiceNow custom credential type |
| Prompt on launch | Variables (for `change_number`, `work_notes`, `snow_state`) |

#### Simulate - Change Process Initiation

| Setting | Value |
|---------|-------|
| Playbook | `test/simulate_change_process.yml` |
| Credential | ServiceNow custom credential type (plus automation orchestrator env vars below) |
| Extra vars | `scenario_list` — `standard`, `high_risk`, or a comma-separated list |

Add the automation orchestrator service account to the simulation credential (or a second one):

```yaml
# Injectors: env
AO_BASE_URL: "{{ AO_BASE_URL }}"
AO_CLIENT_ID: "{{ AO_CLIENT_ID }}"
AO_CLIENT_SECRET: "{{ AO_CLIENT_SECRET }}"
```

## 2. Configure automation orchestrator

### Credentials

Create a model credential for the AI agents (tested with `claude-sonnet-4-6`) and an AAP integration credential for the `aap_job_template` steps.

### Import Workflow

Import `ao/check-mode-change-control.json` (use `playbooks/sync_ao_workflows.yml` from this repository, or import in the automation orchestrator UI).

## 3. Wire AO Workflow Steps

After import, update each step:

1. **Both Task agents** — set the model credential (`YOUR_AO_MODEL_CREDENTIAL_ID`)
2. **All AAP job steps** (`Run Change in Check Mode`, `Push Impact Work Note to Change`, `Run Change for Real`, `Push Close-Out and Close Change`, `Push Rejection Work Note`) — set the AAP integration credential (`YOUR_AO_AAP_CREDENTIAL_ID`); confirm job template names match your AAP
3. Use `${}` automation orchestrator syntax — NOT `{{ }}` Jinja2 syntax

## 4. Validate Integrations

Before the demo, confirm each integration:

- **AAP integration** — launch `Multi-Domain Change - Check` manually from the automation orchestrator or validate the AAP connection in the integration settings
- **ServiceNow REST** — run `Update SNOW Change` once with a test change number and a short work note
- **Webhook** — the `change-request` webhook path exists in the workflow trigger

## 5. Test

### Seed drift (repeat before each demo run)

The demo VM starts compliant, and a compliant VM makes the impact report say "0 changes" —
nothing for the operator to decide. Remove the sysctl config so the check-mode run has a real
change to report (this is what the change "fixes"). Run an ad-hoc command in AAP
(inventory **Demo Inventory**, credential **CI/CD Demo SSH Key**, limit **demo-vm**):

```bash
command: rm -f /etc/sysctl.d/99-change-control.conf
```

With this drift in place the report shows the ideal operator story: the **db** domain
task *will change* (config file absent → created), while **web** and **loadbalancer**
are *verified compliant* and will not be touched.

### Run the demo

Run the simulation job template (`Simulate - Change Process Initiation`) with `scenario_list: standard`.

Expected flow:

1. `Multi-Domain Change - Check` runs — job completes with changed tasks reported, **nothing modified** on the hosts
2. The AI impact analyst writes the decision-grade impact report: **Will change** (current state → desired state), **No change needed** (verified compliant items), blast radius, and a recommendation
3. `Update SNOW Change` attaches the report to the change request as a work note
4. The workflow pauses at **Approve Change Execution** — the operator approves or rejects looking at the report
5. Approve → `Multi-Domain Change - Apply` runs for real → AI close-out analyst compares prediction vs. reality → `Update SNOW Change` pushes the close-out and sets the change request to Closed
6. Reject → a rejection work note is pushed to the change request, hosts untouched

Test the rejection path with `scenario_list: high_risk`.

You can also fire the webhook manually (creates nothing in ServiceNow):

```bash
curl -X POST "https://${AO_HOST}/api/v1/webhooks/change-request" \
  -H "Authorization: Bearer ${AO_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"number": "CHG0030001", "summary": "Multi-domain time-sync hardening", "risk": "low"}'
```
