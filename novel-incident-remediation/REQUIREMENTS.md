# Novel Incident Remediation - Requirements

## Infrastructure

| Component | Required | Notes |
|-----------|----------|-------|
| Ansible Automation Platform | Yes | 2.7+ with Automation Orchestrator |
| ServiceNow instance | Yes | Incident source and update target |
| AAP MCP server | Yes | Gives AI agent read access to job templates for the unknown path |

## AAP Setup

### Job Templates

Create the following job templates in AAP using the playbooks in `aap/playbooks/`:

| Job Template Name | Playbook | Notes |
|-------------------|----------|-------|
| `Incidents \| Gather System Facts` | `gather_incident_facts.yml` | Runs on affected host; publishes metrics as `set_stats` artifacts |
| `Incidents \| Capacity - Disk Cleanup` | `remediate_disk_cleanup.yml` | Disk capacity path |
| `Incidents \| Service Recovery` | `linux_service_recovery.yml` | Service down path |
| `Incidents \| Impact Report` | `incident_impact_report.yml` | Used for service_down and config_drift paths |
| `Incidents \| Log and Report` | `incident_log_and_report.yml` | Unrecognized incident logging |
| `Incidents \| Update Ticket` | `notify_snow.yml` | Used for all SNOW state updates; pass `snow_ticket_state`, `notification_title`, `notification_body` as extra vars |

Attach the appropriate SSH machine credential and ServiceNow credential to each template.

### ServiceNow Credential

All SNOW-touching job templates expect these variables, injected via an AAP credential or extra vars:

| Variable | Description |
|----------|-------------|
| `snow_instance_url` | ServiceNow instance base URL |
| `snow_username` | ServiceNow username |
| `snow_password` | ServiceNow password |

## AO Integrations

### AAP MCP Integration

Required for the `unknown` incident path. The AI agent uses it to search for existing job templates.

Add in AO under Integrations:

| Field | Value |
|-------|-------|
| Integration type | MCP Server |
| Server name | `aap-mcp` |
| API URL | Your AAP MCP server URL |

Enable job template list and retrieve tools. Note the tool UUID - you will need it for `YOUR_AAP_MCP_TOOL_UUID`.

## AO Credential Placeholders

Replace these in `ao/novel-incident-remediation.json` before importing:

| Placeholder | Description |
|-------------|-------------|
| `YOUR_SERVICE_ACCOUNT_ID` | AO service account allowed to trigger the webhook |
| `YOUR_AO_AAP_CREDENTIAL_ID` | AO credential for AAP job template execution (all AAP nodes) |
| `YOUR_AAP_INTEGRATION_ID` | AO integration ID for the AAP connection |
| `YOUR_AO_MODEL_CREDENTIAL_ID` | AO credential for the Claude/LLM model (AI agent nodes) |
| `YOUR_AO_LLM_MODEL_ID` | LLM model ID configured in AO |
| `YOUR_AAP_MCP_TOOL_UUID` | UUID of the AAP MCP job_templates_list tool |
| `YOUR_AO_AAP_MCP_CREDENTIAL_ID` | AO credential for the AAP MCP integration |
| `YOUR_AAP_MCP_INTEGRATION_ID` | AO integration ID for the AAP MCP server |

## Webhook Trigger

The workflow uses a webhook trigger with path `novel-incident-remediation`. After importing, add your AO service account to the trigger's authorized service accounts list in the AO UI.

Expected payload:

```json
{
  "ticket_id": "INC0012345",
  "host": "node1",
  "severity": "2-High",
  "description": "Root filesystem at 94% capacity. Application throwing ENOSPC errors.",
  "incident_type": "capacity_issue"
}
```

Valid `incident_type` values: `capacity_issue`, `service_down`, `config_drift`, `unknown`

## Demo Scenarios

| Scenario | `incident_type` | Expected Path |
|----------|----------------|---------------|
| Disk full | `capacity_issue` | Deterministic: disk cleanup JT runs, SNOW notified |
| Service crashed | `service_down` | Deterministic: impact report, service recovery JT, ticket closed |
| SSH config drift | `config_drift` | Deterministic: impact report, escalated to Change Management |
| Novel/unknown | `unknown` | AI: investigates, enriches SNOW, generates plan, approval, executes |
