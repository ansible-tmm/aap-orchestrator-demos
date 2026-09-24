# AI Incident Triage - ServiceNow Integration

AI-driven incident triage workflow. When a ServiceNow incident fires, an AI agent fetches the full incident record via ServiceNow MCP, classifies severity and risk, then routes to the right response path.

## Workflow

```
Trigger (incident number)
  → AI Triage Agent  [fetches incident via SNOW MCP, adds work note, classifies]
  → Switch (3-way)
      → Auto-Remediate:  AAP job → resolve incident via SNOW MCP
      → Needs Approval:  work note → human approval → AAP job → resolve
      → Inform Only:     enrich ticket, add comment, set In Progress
```

## Features Demonstrated

| Feature | Where |
|---------|-------|
| ServiceNow MCP native integration | All Task agents |
| AI incident classification | Triage Agent |
| Switch (3-way routing) | Route Decision step |
| Human Approval | Approval branch |
| AAP Job Template execution | Both remediation branches |

## Files

| Path | Description |
|------|-------------|
| `ao/snow-incident-response.json` | AO workflow JSON - import into Ansible Automation Orchestrator |
| `aap/playbooks/snow_auto_remediation.yml` | AAP remediation playbook |
| `REQUIREMENTS.md` | Full setup instructions |

## Quick Start

See [REQUIREMENTS.md](REQUIREMENTS.md) for full setup details.

1. Configure ServiceNow MCP integration in AO
2. Replace credential placeholders in `ao/snow-incident-response.json`
3. Import the workflow JSON into AO
4. Create job template `SNOW - Auto Remediation` in AAP using `aap/playbooks/snow_auto_remediation.yml`
5. Trigger with a ServiceNow incident number
