# AAP automation orchestrator demos

Hands-on demos for **Ansible Automation Platform automation orchestrator (AO)** — intelligent workflows that combine Ansible playbooks, AI agents, approvals, and event-driven triggers.

**[Browse demos on GitHub Pages →](https://ansible-tmm.github.io/aap-orchestrator-demos/)**

**[Developer setup & technical docs →](DEVELOPER.md)**

## What is automation orchestrator?

Automation orchestrator is the workflow engine in AAP for visual, multi-step automation:

- **Task agents** — reason and decide using LLMs
- **AAP job template nodes** — run Ansible playbooks
- **Approval nodes** — human-in-the-loop governance
- **Event triggers** — react to Splunk, Prometheus, webhooks, and more
- **Switch nodes** — route on a value, not just success/failure

## Demo catalog

| Demo | Status | Description |
|---|---|---|
| [RHEL CVE Remediation](cve-remediation/) | **Active** | AI triage via Lightspeed MCP → auto-patch dev, approve prod, or investigate with Mattermost report |
| [Multi-OS Cloud Patching](multi-os-cloud-patching/) | **Active** | Playbook orchestration — RHEL and Windows on AWS with snapshot rollback (playbooks from product-demos) |
| [Disk Utilization & Remediation](disk-utilization/) | **Active** | Check disk usage → switch on % → continue, cleanup, EBS expand, or fallback → Mattermost notify |
| [Intelligent Cert Lifecycle](cert-lifecycle/) | **Active** | AI agent picks PEM vs keystore renewal; operator approves; AAP renews and validates |
| [Service State Routing](service-health/) | Coming soon | Check service → switch on state → log OK, start, restart, or install |
| [Patch Severity Routing](patch-management/) | Coming soon | Scan patches → switch on severity → patch now, schedule, batch, or compliant |
| [Expiry Threshold Routing](cert-expiry-switch/) | Coming soon | Cert countdown switch on days remaining (no AI) |
| [Request Type Routing](user-lifecycle/) | Coming soon | User lifecycle form → switch on request type |
| [Risk-Based Routing](risk-based-routing/) | Coming soon | AI risk-tier routing for certificate renewal |
| [Proactive Assessment](proactive-assessment/) | Coming soon | Scheduled scan-before-expiry workflows |
| [AI Incident Triage](ai-incident-triage/) | Coming soon | AI-assisted incident response |
| [Multi-Service Correlation](multi-service-correlation/) | Coming soon | Correlate alerts across services before remediation |
| [Event-Driven xSOS RCA](event-driven-xsos-rca/) | In progress | SQS → EDA → xSOS analysis for unknown issues |

See the [demo marketplace](https://ansible-tmm.github.io/aap-orchestrator-demos/) for the full list including backup, subscription, and kernel compliance scaffolds.

## Use cases by folder

| Demo folder | Focus |
|---|---|
| [cert-lifecycle/](cert-lifecycle/) | Intelligent certificate renewal — AI routing |
| [cert-expiry-switch/](cert-expiry-switch/) | Rule-based cert countdown switch |
| [risk-based-routing/](risk-based-routing/) | AI risk-tier renewal routing |
| [proactive-assessment/](proactive-assessment/) | Scheduled scan-before-expiry |
| [cve-remediation/](cve-remediation/) | Intelligent CVE patching with Lightspeed MCP |
| [multi-os-cloud-patching/](multi-os-cloud-patching/) | Multi-OS cloud patching with snapshot rollback (product-demos playbooks) |
| [disk-utilization/](disk-utilization/) | Proportional disk remediation with switch routing |
| [event-driven-xsos-rca/](event-driven-xsos-rca/) | SQS → EDA → xSOS RCA for unknown issues |
| [ai-incident-triage/](ai-incident-triage/) | AI-assisted incident response |
| [multi-service-correlation/](multi-service-correlation/) | Multi-alert correlation before remediation |
| [service-health/](service-health/) | Service state check → four remediation paths |
| [patch-management/](patch-management/) | Patch severity switch routing |
| [user-lifecycle/](user-lifecycle/) | Identity request type routing |
| [backup-management/](backup-management/) | Backup result routing (partial ≠ fail) |
| [subscription-management/](subscription-management/) | RHEL subscription state routing |
| [kernel-compliance/](kernel-compliance/) | Kernel compliance switch routing |

Categories (cert-rotation, incident-remediation, etc.) are tags on the [demo marketplace](https://ansible-tmm.github.io/aap-orchestrator-demos/) — not filesystem folders.

## Quick links

- **Browse all demos (cards + filters):** https://ansible-tmm.github.io/aap-orchestrator-demos/
- **Setup guides:** [DEVELOPER.md](DEVELOPER.md)
