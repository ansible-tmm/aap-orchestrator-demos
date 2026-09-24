# ServiceNow Incident - AI Triage and Response

## Workflow Overview

```
Trigger (incident number)
  → AI Triage Agent  [fetches incident via SNOW MCP, adds work note, classifies]
  → Switch
      → Auto-Remediate:  AAP job → Resolve incident via SNOW MCP
      → Needs Approval:  Work note → Human Approval → AAP job → Resolve via SNOW MCP
      → Inform Only:     Enrich ticket, add comment, set In Progress via SNOW MCP
```

## Features Demonstrated

| Feature | Where |
|---------|-------|
| ServiceNow MCP native integration | All Task agents |
| AI incident classification | Triage Agent |
| Switch (3-way routing) | Route Decision step |
| Human Approval | Approval branch |
| AAP Job Template execution | Both remediation branches |
| Structured agent output | Triage Agent response_schema |

## AO Setup

### 1. MCP Integration - ServiceNow

Add in AO under Integrations:

| Field | Value |
|-------|-------|
| Integration type | MCP Server |
| Server name / ID | `servicenow-mcp` |
| API URL | `https://rlopez-ao-snow.demoredhat.com/mcp` |
| API key | `5200f0ac03e9142644662b9d1d7a2ea6637f26819beb12a81c2b1319ed005738` |

Enable all tools. Attach this integration to the following steps when importing the workflow:
- `AI Triage Agent`
- `Resolve Incident` (auto branch)
- `Notify - Awaiting Approval`
- `Resolve Incident - Approved`
- `Enrich and Assign`

### 2. Model Credential

Use the same LiteLLM credential as the CVE demo: `b9b3529b-5211-4b9b-90f6-e37c1106919e`

Replace `YOUR_AO_MODEL_CREDENTIAL_ID` in the JSON with this value before importing.

### 3. AAP Credential

Same credential as CVE demo. Replace `YOUR_AO_AAP_CREDENTIAL_ID` in the JSON.

## AAP Setup

### 1. Job Template - SNOW - Auto Remediation

| Field | Value |
|-------|-------|
| Name | `SNOW - Auto Remediation` |
| Playbook | `snow_auto_remediation.yml` |
| Project | Point to a project containing `aap/playbooks/snow_auto_remediation.yml` |
| Inventory | Lab inventory with your test nodes |
| Extra vars prompt | Enable (workflow passes `incident_number`, `affected_system`, `category`, `recommended_action`) |

## ServiceNow Setup

### Test Incidents

Create 3 incidents in `ansible.service-now.com` to cover each demo branch:

**Branch 1 - Auto Remediate (Priority: Critical/High, low-risk)**
- Short description: `Web server nginx not responding on app-server-01`
- Priority: 1 - Critical
- Category: Software
- CI: `app-server-01`

**Branch 2 - Needs Approval (Priority: Critical/High, risky change)**
- Short description: `Database server requires kernel upgrade to resolve memory leak`
- Priority: 1 - Critical
- Category: Software
- CI: `db-server-01`

**Branch 3 - Inform Only (Priority: Moderate/Low)**
- Short description: `Intermittent email delivery delays reported by finance team`
- Priority: 3 - Moderate
- Category: Inquiry / Help

### SNOW Credentials

| Field | Value |
|-------|-------|
| Instance | `ansible.service-now.com` |
| Username | `mcp-snow-svc` |
| Password | `pnUt82#J72P` |

## Importing the Workflow

1. Replace placeholder values in `ao/snow-incident-response.json`:
   - `YOUR_AO_MODEL_CREDENTIAL_ID`
   - `YOUR_AO_AAP_CREDENTIAL_ID`
2. Import JSON into AO
3. Attach the `servicenow-mcp` integration to all Task agents listed above
4. Enable all SNOW MCP tools on each step
5. Trigger with the incident number of one of the three test incidents
