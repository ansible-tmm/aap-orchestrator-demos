# Ticket Enrichment Demo - Setup Guide

## Infrastructure Required

| Component | Purpose | How to Provision |
|-----------|---------|------------------|
| AAP 2.7 with AO | Controller + automation orchestrator | `aws-aap-containerized` repo or existing AAP install |
| Demo VM | RHEL 9 EC2 target host for remediation playbooks | EC2 t3.small in `us-east-1` (or your region) |
| ServiceNow | Incident ingress and ticket management | Developer instance or existing SNOW environment |
| ServiceNow MCP | AI agents read/write incidents via MCP integration | Configure in automation orchestrator |
| AI credential | Task agents (triage + enrich-and-assign) | Any supported model; tested with `claude-sonnet-4-6` |

## Architecture

```text
ServiceNow (webhook) → AI Triage Agent → Update SNOW Ticket → Route Decision (switch)
  ├── Auto Remediate    → Run Auto Remediation (dynamic JT) → Update SNOW Ticket
  ├── Needs Approval    → Approve Remediation → Run Approved Remediation → Update SNOW Ticket
  └── Inform Only       → Enrich and Assign (agent) → Update SNOW Ticket
```

## Step-by-Step Setup

### 1. Provision Demo VM

```bash
# Create EC2 key pair
aws ec2 create-key-pair --key-name ao-ticket-demo-key \
  --query 'KeyMaterial' --output text --region us-east-1 > ao-ticket-demo-key.pem
chmod 600 ao-ticket-demo-key.pem

# Launch RHEL 9 instance (adjust AMI for your region)
aws ec2 run-instances \
  --image-id ami-0d85f16af633ab171 \
  --instance-type t3.small \
  --key-name ao-ticket-demo-key \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ao-ticket-demo-vm}]' \
  --region us-east-1

# Export connection details for inventory
export TICKET_DEMO_VM_IP=<VM_PUBLIC_IP>
export TICKET_DEMO_SSH_KEY=$PWD/ao-ticket-demo-key.pem

# Verify SSH
ssh -i "$TICKET_DEMO_SSH_KEY" ec2-user@"$TICKET_DEMO_VM_IP" 'hostname'
```

### 2. Configure ServiceNow

1. **ServiceNow instance** — use a developer instance or existing environment.
2. **MCP integration** — configure ServiceNow MCP in automation orchestrator so the Task agents can query and update incidents.
3. **Test incident** — create a test incident to use during demos. The webhook payload only needs `incident_number`.

### 3. Configure AAP Project and Inventory

1. **Project** — sync this repo (or `ticket-enrichment/` subtree) from Git.
2. **Inventory** — create a host for the demo VM:

| Host | `ansible_host` | Notes |
|------|----------------|-------|
| `ticket-demo-vm` | VM public IP | `ec2-user`, SSH key credential |

3. **ServiceNow credentials** — store as extra vars or a custom credential type:

| Variable | Purpose |
|----------|---------|
| `snow_instance_url` | ServiceNow instance base URL |
| `snow_username` | ServiceNow service account username |
| `snow_password` | ServiceNow service account password |

### 4. Register Job Templates

Create three job templates from `ticket-enrichment/playbooks/`:

| Name | Playbook | Runs on | Notes |
|------|----------|---------|-------|
| Incidents \| Update Ticket | `update_snow_ticket.yml` | localhost | Posts work notes and updates ticket state via SNOW API |
| Incidents \| Capacity - Disk Cleanup | `remediate_disk_cleanup.yml` | `ticket-demo-vm` | One of the dynamic templates the triage agent can select |
| Incidents \| High CPU - Process Cleanup | `remediate_process_cleanup.yml` | `ticket-demo-vm` | One of the dynamic templates the triage agent can select |

**Credentials:**

- SSH Machine credential on remediation playbooks (disk cleanup, process cleanup)
- No SSH needed on Update Ticket — runs on localhost against the SNOW API

**Update Ticket extra vars** — pass from AO or set on the job template:

| Variable | Purpose |
|----------|---------|
| `ticket_id` | ServiceNow incident number (e.g., `INC0010001`) |
| `notification_title` | Work note heading from triage agent |
| `notification_body` | Work note body from triage agent |
| `snow_ticket_state` | SNOW state value (`2` = In Progress, `6` = Resolved) |

Enable **Prompt on launch → Extra Variables** on the Update Ticket template so AO can pass values from upstream steps.

### 5. Configure AI Credential

1. Create an AI credential in automation orchestrator for your chosen model provider.
2. Tested with `claude-sonnet-4-6` — any supported model works on both Task agents.
3. Configure ServiceNow MCP and AAP MCP tool connections on the **AI Triage Agent** step.
4. Configure ServiceNow MCP tool connections on the **Enrich and Assign** step.

### 6. Import AO Workflow

Import the workflow JSON into automation orchestrator:

| File | Description |
|------|-------------|
| [`ao/ticket-enrichment.json`](ao/ticket-enrichment.json) | Three-way switch: auto-remediate, needs-approval, inform-only |

**After import, update environment-specific values:**

1. `credential_id` on each step — replace `REPLACE_WITH_AAP_CREDENTIAL_ID` and `REPLACE_WITH_AI_CREDENTIAL_ID`
2. `integration_id` on AAP job steps — replace `REPLACE_WITH_INTEGRATION_ID`
3. ServiceNow credentials in extra vars — replace `YOUR_SNOW_*` placeholders
4. Re-select MCP tools on both Task agents (tool UUIDs are environment-specific)

### 7. Configure the Webhook

- Path: `/snow-incident` (as defined in the workflow JSON)
- ServiceNow (or a bridge) POSTs incident payload to the automation orchestrator webhook URL
- Required payload field: `incident_number` (string)

Example test payload:

```json
{
  "incident_number": "INC0010001"
}
```

### 8. Configure the Switch Step

| Switch port | Condition | Path |
|-------------|-----------|------|
| Auto Remediate | `route == 'auto_remediate'` | Dynamic AAP job → Update SNOW (resolved) |
| Needs Approval | `route == 'needs_approval'` | Approval gate → Dynamic AAP job → Update SNOW (resolved) |
| Inform Only | `route == 'inform_only'` | Enrich and Assign agent → Update SNOW |

The switch routes on `${triage_agent.result.content.route}` — this is configured in the imported workflow JSON.

## Dynamic Job Template

The **Run Auto Remediation** and **Run Approved Remediation** steps use an expression for the job template name:

```text
${triage_agent.result.content.job_template_name}
```

The triage agent prompt instructs the model to discover available AAP job templates via AAP MCP and select the best match for the incident. Register job templates with descriptive names (e.g., `Incidents | Capacity - Disk Cleanup`) so the agent can match by incident category.

## Verification

```bash
# Test auto-remediate: fire a P1 disk-cleanup incident
curl -X POST https://<AO_HOST>/api/v1/webhooks/snow-incident \
  -H "Content-Type: application/json" \
  -d '{"incident_number": "INC0010001"}'
# Expected: Triage → Update Ticket (In Progress) → Auto Remediate → Disk Cleanup runs → Update Ticket (Resolved)

# Test needs-approval: fire a P2 risky change incident
# Expected: Triage → Update Ticket → Approval gate (pauses) → Approved → Remediation → Update Ticket (Resolved)

# Test inform-only: fire a P4 informational incident
# Expected: Triage → Update Ticket → Enrich and Assign agent (searches related incidents, adds work notes) → Update Ticket
```

## Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| AAP Gateway | 443 / 8444 | AAP UI and API |
| AO UI | 8080 | Automation orchestrator web interface |
| ServiceNow | 443 | SNOW API for ticket operations |
| SSH | 22 | Ansible connection to demo VM |
