# Multi-Service Correlation

**Status: Active** — playbooks and AO workflow JSON included.

Multiple correlated alerts arrive across services. The workflow correlates them, identifies root cause when possible, and routes to targeted remediation or AI-assisted triage when not.

## Workflow

```mermaid
flowchart LR
  A[Multiple correlated alerts] --> B[Correlate services]
  B --> C{Root cause identified?}
  C -->|Yes| D[Targeted remediation]
  C -->|No| E[AI triage agent]
  D --> F[Validate recovery]
  E --> F
  F --> G[Notify operators]
```

## Playbooks

| Playbook |
|---|
| [`correlate_alerts.yml`](playbooks/correlate_alerts.yml) |
| [`notify_operators.yml`](playbooks/notify_operators.yml) |
| [`targeted_remediation.yml`](playbooks/targeted_remediation.yml) |
| [`validate_recovery.yml`](playbooks/validate_recovery.yml) |
