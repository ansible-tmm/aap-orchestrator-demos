# Multi-Service Correlation Demo - Full Setup Guide

Multiple correlated alerts arrive across services. The workflow correlates them,
identifies a root cause when possible, and routes to **targeted remediation** when
a root cause is found, or to an **AI Task-agent triage path** when it is not. Both
paths converge on recovery validation and operator notification.

## Infrastructure Required

| Component | Purpose | How to Provision |
|-----------|---------|------------------|
| AAP 2.7 with AO | Controller + automation orchestrator | `aws-aap-containerized` repo or existing AAP install |
| Demo VM(s) | RHEL 9 target host(s) running the correlated services (e.g. `httpd`, `postgres`) that targeted/AI remediation restarts and validates | EC2 t3.small in `us-east-1` (or your region) |
| LLM / model connection | Backs the **AI Triage Agent** (`agentic`) node — analyzes the alert pattern and returns a JSON root-cause recommendation | Configure a model/LLM connection in AO and bind it to the agentic node |
| Mattermost | Operator notification with correlation summary | Container on bastion (or reuse an existing Mattermost instance) |

## Step-by-Step Setup

### 1. Provision Demo VM(s)

```bash
cd ~/work/src/aap-orchestrator-demos

# Create EC2 key pair
aws ec2 create-key-pair --key-name ao-correlation-demo-key \
  --query 'KeyMaterial' --output text --region us-east-1 > ao-correlation-demo-key.pem
chmod 600 ao-correlation-demo-key.pem

# Launch RHEL 9 instance (adjust AMI for your region)
aws ec2 run-instances \
  --image-id ami-0d85f16af633ab171 \
  --instance-type t3.small \
  --key-name ao-correlation-demo-key \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ao-correlation-demo-vm}]' \
  --region us-east-1

export CORR_DEMO_VM_IP=<VM_PUBLIC_IP>
export CORR_DEMO_SSH_KEY=$PWD/ao-correlation-demo-key.pem

# Verify SSH
ssh -i "$CORR_DEMO_SSH_KEY" ec2-user@"$CORR_DEMO_VM_IP" 'systemctl --version'
```

Install and enable the services referenced by the alert payloads (for the default
payload, `httpd` and `postgres`) so `targeted_remediation.yml` has something to
restart and `validate_recovery.yml` has something to validate:

```bash
ssh -i "$CORR_DEMO_SSH_KEY" ec2-user@"$CORR_DEMO_VM_IP" \
  'sudo dnf install -y httpd && sudo systemctl enable --now httpd'
```

### 2. Configure AAP Project and Inventory

1. **Project** — sync this repo (or the `multi-service-correlation/` subtree) from Git.
2. **Inventory** — create host(s) matching the `host` values you will send in the
   `alert_payloads` trigger input (the default payload uses `node1`):

| Host | `ansible_host` | Notes |
|------|----------------|-------|
| `node1` | VM public IP | `ec2-user`, SSH key credential |

The correlation playbook runs on `localhost`. `targeted_remediation.yml` and
`validate_recovery.yml` use `hosts: "{{ _host | default('all') }}"`, so scope their
job templates (or pass `_host`) to the affected hosts.

3. **Optional variable overrides:**

| Variable | Default | Used by | Purpose |
|----------|---------|---------|---------|
| `correlation_window_seconds` | `300` | `correlate_alerts.yml` | Correlation window |
| `validation_retries` | `3` | `validate_recovery.yml` | Recovery re-check attempts |
| `validation_delay` | `10` | `validate_recovery.yml` | Seconds between re-checks |

### 3. Register Job Templates

Create four job templates from `multi-service-correlation/playbooks/`. The
**Name** column must match the `job_template_name` values in the AO workflow JSON
exactly.

| Job Template Name (from AO JSON) | Playbook | Runs on |
|----------------------------------|----------|---------|
| `Multi-Service - Correlate Alerts` | `correlate_alerts.yml` | localhost |
| `Multi-Service - Targeted Remediation` | `targeted_remediation.yml` | affected host(s) |
| `Multi-Service - Validate Recovery` | `validate_recovery.yml` | affected host(s) |
| `Notify Chatroom` | `notify_operators.yml` | localhost |

Note: both the targeted path (`Targeted Remediation` node) and the AI path
(`AI-Guided Remediation` node) map to the **same** `Multi-Service - Targeted
Remediation` job template — the AI path simply feeds it the agent's `root_cause`
instead of the correlation playbook's. Likewise both validate nodes use the single
`Multi-Service - Validate Recovery` template.

**Credentials:**

- SSH Machine credential on `Multi-Service - Targeted Remediation` and
  `Multi-Service - Validate Recovery` (they run against the affected hosts and use
  `become: true`).
- No SSH needed on `Multi-Service - Correlate Alerts` or `Notify Chatroom` — both
  run on localhost.

**Prompt on launch** — enable **Prompt on launch → Extra Variables** on all four
templates so AO can pass the mapped `extra_vars` from upstream nodes and the trigger.

### 4. Configure Notify (Mattermost)

`notify_operators.yml` posts a Mattermost attachment (color-coded: green when
`recovery_status == ok`, yellow when `correlation_result == root_cause_found`, red
otherwise). Provide these to the `Notify Chatroom` job template:

| Variable | Purpose |
|----------|---------|
| `api_chat_token` | Mattermost bot API key (required by `community.general.mattermost`) |
| `mattermost_server` | Host:port (default `44.209.231.244:8065`) |

```bash
# Login (adjust host and credentials)
MM_TOKEN=$(curl -s http://<bastion>:8065/api/v4/users/login \
  -H "Content-Type: application/json" \
  -d '{"login_id":"admin","password":"changeme123"}' -D - | grep "^token:" | awk '{print $2}')

# Create a bot account + token, then store it as api_chat_token on the notify job template
```

### 5. Configure the AI Triage Agent Model Connection

The `AI Triage Agent` node is an `agentic` node — it is **not** an AAP job
template. It sends a prompt built from the correlation artifacts (`alert_hosts`,
`correlated_services`, `alert_count`, `same_host`) and expects a JSON response
matching this `response_schema`: `root_cause` (string), `confidence` (number),
`investigate_first` (string), `recommended_actions` (array of strings), and
`reasoning` (string).

In automation orchestrator, configure a model/LLM connection and bind it to this
node so it can execute. Its output field `root_cause` is consumed downstream by the
`AI-Guided Remediation` node as `${ai_triage_agent.result.content.root_cause}`.

## Import AO Workflow

Import the workflow JSON into automation orchestrator:

| File | Switch routes on | Use when |
|------|------------------|----------|
| [`ao/multi-service-correlation-201.json`](ao/multi-service-correlation-201.json) | `correlation_result` (`root_cause_found` / `unknown`) | Demonstrating correlated-alert routing with an AI fallback |

**After import, update environment-specific values:**

1. `job_template` / job template IDs on each AAP job node so they resolve to your
   Controller's templates (the JSON references them by `job_template_name` — confirm
   the names match Step 3).
2. `credential_id` on each node for your Controller's credentials.
3. The **model/LLM connection** bound to the `AI Triage Agent` node.
4. `organization_name` is `Default` throughout — change if your org differs.

## Configure the Switch Node

The switch node is named **Root Cause Found?** and branches on the
`correlation_result` artifact published by `Multi-Service - Correlate Alerts`.

| Switch label (port) | Condition | Path |
|---------------------|-----------|------|
| `root_cause_found` (`case_0`) | `${correlate_alerts.artifacts.correlation_result} == 'root_cause_found'` | Targeted Remediation → Validate Recovery (Targeted) → Notify Operators |
| `unknown` (`case_1`) | `${correlate_alerts.artifacts.correlation_result} == 'unknown'` | AI Triage Agent → AI-Guided Remediation → Validate Recovery (AI) → Notify Operators |

The correlation playbook sets `correlation_result = root_cause_found` when **all
alerts share one host and there is more than one alert**, or when a
**database-service alert and an app/web-service alert both appear** (cascading
dependency pattern). Otherwise it sets `unknown`.

## Test / Verification

Exercise both branches through the manual trigger **Correlated Alert Event**, whose
`input_schema` requires a single field, `alert_payloads` — a JSON **string**
containing an array of alert objects with `host`, `service`, `severity`, and
`message` fields.

**Root-cause-found branch (targeted path)** — use the trigger default, or any
payload where every alert is on the same host with more than one alert (or a DB +
app pair). The default payload already satisfies this (two alerts on `node1`,
`httpd` + `postgres`):

```json
[
  {"host":"node1","service":"httpd","severity":"critical","message":"Service down"},
  {"host":"node1","service":"postgres","severity":"critical","message":"Connection refused"}
]
```

Expected: switch takes `root_cause_found` → `Multi-Service - Targeted Remediation`
restarts `httpd`,`postgres` → `Multi-Service - Validate Recovery` → yellow/green
Mattermost notification.

**Unknown branch (AI Task-agent path)** — send a single alert, or alerts spread
across multiple hosts with no DB+app dependency pattern, so `correlation_result`
becomes `unknown`:

```json
[
  {"host":"node1","service":"chronyd","severity":"warning","message":"Time skew"},
  {"host":"node2","service":"sshd","severity":"warning","message":"High latency"}
]
```

Expected: switch takes `unknown` → `AI Triage Agent` returns a JSON root-cause
recommendation → `AI-Guided Remediation` (targeted-remediation template fed the
agent's `root_cause`) → `Multi-Service - Validate Recovery` → Mattermost notification.

Confirm on the `Correlate Alerts` node output that these artifacts are published for
the switch and downstream nodes: `correlation_result`, `root_cause`, `alert_count`,
`alert_hosts`, `correlated_services`, and `same_host`.

## Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| AAP Gateway | 443 / 8444 | AAP UI and API |
| AO UI | 8080 | automation orchestrator web interface |
| Mattermost | 8065 | Operator notifications |
| SSH | 22 | Ansible connection to demo host(s) |
