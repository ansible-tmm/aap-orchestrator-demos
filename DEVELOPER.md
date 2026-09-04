# Developer Guide

Technical reference for setting up, extending, and running demos in this repository.

## Quick start

```bash
git clone https://github.com/ansible-tmm/aap-orchestrator-demos.git
cd aap-orchestrator-demos

ansible-galaxy collection install -r collections/requirements.yml

# Cert lifecycle setup
cat cert-lifecycle/SETUP_GUIDE.md

# Disk utilization
cat disk-utilization/README.md
```

## How demos are organized

**One demo = one top-level folder.** Category labels (cert-rotation, incident-remediation, etc.) live in `_data/demos.yml` for marketplace filtering — not in the filesystem.

```
<demo-slug>/
  README.md           # Demo docs and setup
  ao/                 # automation orchestrator workflow JSON (importable)
  playbooks/          # Ansible playbooks registered as AAP job templates
  setup/              # Playbooks to provision the demo environment (where applicable)
  inventory/          # Ansible inventory
  group_vars/         # Variable defaults
```

## Repository structure

```
aap-orchestrator-demos/
├── README.md
├── DEVELOPER.md
├── _data/demos.yml          # Marketplace catalog (slug, category, paths)
├── cert-lifecycle/          # Active — category: cert-rotation
├── cert-expiry-switch/      # Coming soon
├── risk-based-routing/      # Coming soon
├── proactive-assessment/    # Coming soon
├── cve-remediation/         # Active
├── disk-utilization/        # Active
├── event-driven-xsos-rca/   # In progress — category: incident-remediation
├── ai-incident-triage/      # Coming soon
├── ticket-enrichment/       # Coming soon — Arcade ready, assets pending upload
├── multi-service-correlation/
├── service-health/
├── patch-management/
├── multi-os-cloud-patching/   # Active — category: patching
├── user-lifecycle/
├── backup-management/
├── subscription-management/
├── kernel-compliance/
└── extensions/eda/rulebooks/   # EDA rulebooks (AAP discovery path)
```

## Cert rotation (Intelligent Cert Lifecycle)

**Story:** Two certificates expire simultaneously on production services. Splunk detects both and fires alerts to AO. A single AI-powered workflow handles both, automatically selecting the correct renewal strategy for each certificate type.

- **nginx** on port 443 uses a **PEM certificate** → agent selects `Renew Certificate` template
- **API server** on port 8443 uses a **Java keystore** → agent selects `Renew Java Keystore Certificate` template

The agent discovers available job templates from AAP, reads host variables, checks past job run history, and reasons about the correct approach — **intelligent routing without hardcoded if-statements**.

```
Splunk Alert (cert expired)
    |
AO Webhook Trigger
    |
Plan Renewal (AI agent - queries AAP, selects correct template)
    |
Approve Renewal (operator reviews agent analysis + confidence %)
    |
Run Renewal Job (dynamic: agent-selected template)
    |
Validate Renewal (TLS handshake check)
```

## Disk utilization

**Story:** Check disk usage on a mount, route by how full the filesystem is, remediate proportionally, notify Mattermost.

```
Check disk usage → Switch on % → Continue | Cleanup | Expand | Fallback → Notify
```

See [disk-utilization/SETUP_GUIDE.md](disk-utilization/SETUP_GUIDE.md) for environment setup, JT IDs, AO workflow import, and `test_disk_use_percent` branch testing.

## AO vs AAP workflow comparison

| Capability | AAP Workflow | AO Workflow |
|---|---|---|
| Template selection | Hardcoded in workflow node | AI agent discovers and selects at runtime |
| Multi-cert routing | Requires conditions per cert type | Agent reasons about cert type automatically |
| Threshold routing | Nested success/failure nodes | Switch node routes on `disk_use_percent` with comparison expressions |
| Approval context | Basic approve/deny | Agent analysis, confidence %, blast radius |
| Event triggers | Requires EDA rulebook | Native webhook triggers (Splunk, Prometheus, etc.) |
| Visual builder | YAML defined | Drag-and-drop with live execution view |

## Infrastructure requirements (active demos)

| Component | Details |
|---|---|
| AAP 2.7+ with AO | Controller + automation orchestrator |
| Demo VM | 1x RHEL 9, t3.small or equivalent |
| HashiCorp Vault | Container on demo VM (cert demo; provisioned automatically) |
| Splunk | Container on bastion/monitoring host (cert demo) |
| LiteLLM | AI proxy for AO agent nodes (cert demo) |
| AWS credentials | Execution environment for EBS expand (disk demo) |
| Mattermost | API token on notify job template (disk demo) |
| DNS | `certdemo.demoredhat.com` pointing to demo VM (cert demo) |

## GitHub Pages site

The demo marketplace at [ansible-tmm.github.io/aap-orchestrator-demos](https://ansible-tmm.github.io/aap-orchestrator-demos/) is built with Jekyll from this repo. Demo cards are defined in [`_data/demos.yml`](_data/demos.yml).

**Featured cards:** The marketplace Featured section uses a 3-column grid — keep exactly **3** demos with `featured: true`. All other demos appear in the smaller **All demos** grid (active first). See [CLAUDE.md](CLAUDE.md).

Local build:

```bash
bundle install
bundle exec jekyll build
open _site/index.html
```
