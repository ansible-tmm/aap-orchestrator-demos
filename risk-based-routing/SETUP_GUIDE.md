# Certificate Rotation 201: Risk-Based Routing - Full Setup Guide

This demo extends the certificate expiry workflow with an AI risk assessment node
that classifies each renewal as **low**, **medium**, or **high** risk, then uses a
switch node to route each tier down a different remediation path (auto-renew,
notify-and-renew, or approval-required).

## Infrastructure Required

| Component | Purpose | How to Provision |
|-----------|---------|------------------|
| AAP 2.7 with AO | Controller + automation orchestrator (includes the agentic/AI node used for risk scoring) | `aws-aap-containerized` repo or existing AAP install |
| Demo VM(s) | RHEL 9 target host(s) that own the TLS certificate to renew and validate | EC2 t3.small in `us-east-1` (or your region) |
| `community.crypto` collection | Key/CSR/cert generation on the renewal playbooks | Bundled in the execution environment, or install into the EE |
| Mattermost | Risk-tier-colored renewal notifications | Container on bastion (or reuse an existing Mattermost instance) |

## Step-by-Step Setup

### 1. Provision Demo VM

```bash
cd ~/work/src/aap-orchestrator-demos

# Create EC2 key pair
aws ec2 create-key-pair --key-name ao-cert-demo-key \
  --query 'KeyMaterial' --output text --region us-east-1 > ao-cert-demo-key.pem
chmod 600 ao-cert-demo-key.pem

# Launch RHEL 9 instance (adjust AMI for your region)
aws ec2 run-instances \
  --image-id ami-0d85f16af633ab171 \
  --instance-type t3.small \
  --key-name ao-cert-demo-key \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ao-cert-demo-vm}]' \
  --region us-east-1

# Export connection details for inventory
export CERT_DEMO_VM_IP=<VM_PUBLIC_IP>
export CERT_DEMO_SSH_KEY=$PWD/ao-cert-demo-key.pem

# Verify SSH
ssh -i "$CERT_DEMO_SSH_KEY" ec2-user@"$CERT_DEMO_VM_IP" 'hostname -f'
```

The renewal playbooks write to standard RHEL PKI locations: certificates in
`/etc/pki/tls/certs` and private keys in `/etc/pki/tls/private`. They use
`become: true`, so the SSH user must have sudo. Certificates are self-signed for
the demo, so no external CA is required.

### 2. Configure AAP Project and Inventory

1. **Project** — sync this repo (or the `risk-based-routing/` subtree) from Git.
2. **Inventory** — create the host(s) referenced by the workflow trigger. The
   trigger `host` field defaults to `node1`, and the renewal/validation playbooks
   run against the `webservers` group by default (`hosts: "{{ _host | default('webservers') }}"`).

| Host | `ansible_host` | Group | Notes |
|------|----------------|-------|-------|
| `node1` | VM public IP | `webservers` | `ec2-user`, SSH key credential |

3. **Host / group variables** (optional overrides accepted by the playbooks):

| Variable | Default | Purpose |
|----------|---------|---------|
| `cert_domain` | `ansible_fqdn` | Certificate common name / file basename |
| `cert_dir` | `/etc/pki/tls/certs` | Where the `.crt` lives |
| `cert_key_dir` | `/etc/pki/tls/private` | Where the `.key` lives |
| `cert_valid_days` | `365` | Validity period for the self-signed cert |
| `validate_port` | `443` | Port for the TLS handshake check |

### 3. Register Job Templates

Create job templates from `risk-based-routing/playbooks/`. The names below must
match the `job_template_name` values in
[`ao/risk-based-routing-201.json`](ao/risk-based-routing-201.json) exactly, or the
AO nodes will fail to resolve.

| Job Template Name | Playbook | Runs on | Used by node(s) |
|-------------------|----------|---------|-----------------|
| `Cert - Auto Renew` | `auto_renew.yml` | `webservers` | Auto-Renew (Low Risk) |
| `Cert - Notify and Renew` | `notify_renew.yml` | `webservers` | Notify + Renew (Medium Risk), Renew After Approval (High Risk) |
| `Cert - Validate TLS` | `validate_tls.yml` | `webservers` | Validate TLS (Low / Medium / High) |
| `Notify Chatroom` | `notify_chatroom.yml` | localhost | Notify Chatroom (final step) |

> Note: `Cert - Notify and Renew` is reused by both the medium-risk path and the
> post-approval high-risk path, so only one job template is needed for both.
>
> The repo also ships `playbooks/assess_risk.yml`. In this workflow the AI/agentic
> node ("AI Risk Assessment") performs the scoring inline, so `assess_risk.yml` is
> **not** wired into the imported JSON. It is provided as an optional helper if you
> want to publish `risk_tier` from a regular job template instead of the AI node
> (register it as `Cert - Assess Risk` and enable Prompt on launch → Extra Variables).

**Credentials:**

- SSH Machine credential on the Linux playbooks (`Cert - Auto Renew`,
  `Cert - Notify and Renew`, `Cert - Validate TLS`). These use `become: true`, so
  enable privilege escalation on the credential or the templates.
- No SSH needed on `Notify Chatroom` — it runs on localhost.

**Notify template extra vars** — set on the `Notify Chatroom` JT or pass from AO:

| Variable | Purpose |
|----------|---------|
| `api_chat_token` | Mattermost bot API token |
| `mattermost_server` | Host:port (default `44.209.231.244:8065`) |

Enable **Prompt on launch → Extra Variables** on `Notify Chatroom` (and on the
renew/validate templates) so AO can pass `cert_domain`, `risk_tier`, `reasoning`,
and `confidence` from the upstream nodes.

### 4. Configure Mattermost

```bash
# Login (adjust host and credentials)
MM_TOKEN=$(curl -s http://<bastion>:8065/api/v4/users/login \
  -H "Content-Type: application/json" \
  -d '{"login_id":"admin","password":"changeme123"}' -D - | grep "^token:" | awk '{print $2}')

# Get team and channel IDs
TEAM_ID=$(curl -s http://<bastion>:8065/api/v4/teams \
  -H "Authorization: Bearer ${MM_TOKEN}" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")

CHANNEL_ID=$(curl -s "http://<bastion>:8065/api/v4/teams/${TEAM_ID}/channels" \
  -H "Authorization: Bearer ${MM_TOKEN}" | python3 -c "import sys,json; [print(c['id']) for c in json.load(sys.stdin) if c['name']=='town-square']")

# Create a bot account and token, or use an incoming webhook.
# Store the bot token as api_chat_token on the Notify Chatroom job template.
```

The `notify_chatroom.yml` playbook colors the Mattermost attachment by risk tier:
green (`#22c55e`) for low, yellow (`#eab308`) for medium, and red (`#ef4444`) for
high, and includes the domain, renewal type, status, validation result, days
remaining, host(s), and the AI reasoning.

### 5. Import AO Workflow

Import the workflow JSON into automation orchestrator:

| File | Routes on | Trigger inputs |
|------|-----------|----------------|
| [`ao/risk-based-routing-201.json`](ao/risk-based-routing-201.json) | `risk_tier` from the AI Risk Assessment node (`low` / `medium` / `high`) | `host` (default `node1`), `cert_domain` |

Flow: **Cert Renewal Request** (manual trigger) → **AI Risk Assessment**
(agentic node) → **Route by Risk Tier** (switch) → tier-specific renewal → **Validate TLS** →
**Notify Chatroom**. The high-risk branch inserts an **Approve High-Risk Renewal**
approval gate before the renewal runs.

**After import, update environment-specific values:**

1. `job_template` / job template resolution on each AAP job node — confirm the
   names match your Controller (they are `Cert - Auto Renew`, `Cert - Notify and Renew`,
   `Cert - Validate TLS`, and `Notify Chatroom`).
2. `credential_id` on each node so it points at your SSH Machine credential (and
   any Mattermost/vault credential you use). These are intentionally omitted from
   the exported JSON and must be set to match your Controller.
3. `organization_name` on each node — the export uses `Default`.

### 6. Configure the Switch Node

The switch node **Route by Risk Tier** evaluates
`${risk_agent.result.content.risk_tier}` and routes to one of three ports. Each
row below maps the switch label/condition to the job template it invokes.

| Switch label | Condition | Remediation path (job template) | Follow-up | Notify color |
|--------------|-----------|---------------------------------|-----------|--------------|
| `low` | `risk_tier == 'low'` | Auto-Renew (Low Risk) → `Cert - Auto Renew` | Validate TLS (Low) | green |
| `medium` | `risk_tier == 'medium'` | Notify + Renew (Medium Risk) → `Cert - Notify and Renew` | Validate TLS (Medium) | yellow |
| `high` | `risk_tier == 'high'` | Approve High-Risk Renewal (approval gate) → Renew After Approval → `Cert - Notify and Renew` | Validate TLS (High) | red |

All three branches converge on the final **Notify Chatroom** (`Notify Chatroom`)
step. The high-risk path only proceeds past the approval gate once a workflow
approver clicks **Approve** in the AO/Controller UI.

### 7. Test / Verification

Launch the workflow from the AO UI using the manual trigger and set the trigger
inputs `host` and `cert_domain`. To exercise a specific switch branch
deterministically, drive the AI Risk Assessment toward a tier — pass a
`cert_domain` whose characteristics match the prompt's rubric, or (for a fully
deterministic demo) swap the agentic node for the `Cert - Assess Risk` job template
and pass `risk_tier` directly as an extra var (`assess_risk.yml` accepts and
publishes `risk_tier`, `cert_domain`, `cert_type`, `days_remaining`, `confidence`,
`blast_radius`, and `reasoning`).

| Branch to test | How to trigger | Expected result |
|----------------|----------------|-----------------|
| Low | `cert_domain` = internal, single-service, non-prod cert (>30 days) — or force `risk_tier=low` | Auto-Renew runs with no approval → Validate TLS (Low) → **green** Mattermost message |
| Medium | `cert_domain` = production cert, limited blast radius (7-30 days) — or force `risk_tier=medium` | Notify + Renew runs → Validate TLS (Medium) → **yellow** Mattermost message |
| High | `cert_domain` = wildcard / externally-facing / multi-service (<7 days) — or force `risk_tier=high` | Workflow pauses at approval gate; after **Approve**, Renew After Approval runs → Validate TLS (High) → **red** Mattermost message |

Verify on the target host after a run:

```bash
ssh -i "$CERT_DEMO_SSH_KEY" ec2-user@"$CERT_DEMO_VM_IP" \
  'sudo openssl x509 -in /etc/pki/tls/certs/<cert_domain>.crt -noout -subject -dates'
```

The `Cert - Validate TLS` step publishes `validation_passed` (true when
`days_remaining > 0`) and `days_remaining` as artifacts, which flow into the final
Mattermost notification.

## Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| AAP Gateway | 443 / 8444 | AAP UI and API |
| AO UI | 8080 | automation orchestrator web interface |
| Mattermost | 8065 | Chat notifications |
| SSH | 22 | Ansible connection to demo VM(s) |
| TLS validation | 443 (`validate_port`) | `openssl s_client` handshake check in `validate_tls.yml` |
