# Proactive Assessment Demo (Cert Rotation 301) - Full Setup Guide

This demo runs a **scheduled** nightly scan of the certificate estate. The scan
publishes a result artifact, an AO switch routes on that result to either a
proactive renewal or an all-clear log, and both paths converge on a compliance
report and a Mattermost notification.

## Infrastructure Required

| Component | Purpose | How to Provision |
|-----------|---------|------------------|
| AAP 2.7 with AO | Controller + automation orchestrator | `aws-aap-containerized` repo or existing AAP install |
| Demo VM | RHEL 9 EC2 target host holding certificates under `/etc/pki/tls/certs`, `/etc/ssl/certs`, `/etc/nginx/ssl` | EC2 t3.small in `us-east-1` (or your region) |
| OpenSSL on target | Read cert expiry (`openssl x509`) and generate self-signed renewals | Preinstalled on RHEL 9 |
| Mattermost | Scan-result notifications | Container on bastion (or reuse an existing Mattermost instance) |

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
ssh -i "$CERT_DEMO_SSH_KEY" ec2-user@"$CERT_DEMO_VM_IP" 'ls -l /etc/pki/tls/certs'
```

The scan playbook searches `/etc/pki/tls/certs`, `/etc/ssl/certs`, and
`/etc/nginx/ssl` for `*.crt` and `*.pem` files. To exercise the `needs_renewal`
branch, seed at least one cert that expires within the window (see
[Test / Verification](#test--verification)).

### 2. Configure AAP Project and Inventory

1. **Project** — sync this repo (or the `proactive-assessment/` subtree) from Git.
2. **Inventory** — create a host for the target VM:

| Host | `ansible_host` | Notes |
|------|----------------|-------|
| `cert-demo-vm` | VM public IP | `ec2-user`, SSH key credential, privilege escalation enabled |

The scan, renew, and log-OK plays run against `{{ _host | default('all') }}`
with `become: true` (log-OK uses `become: false`). The compliance report and
notify plays run on `localhost`.

3. **Host / extra variables** (optional overrides):

| Variable | Default | Used by | Purpose |
|----------|---------|---------|---------|
| `expiry_window_days` | `30` | scan, renew, log-ok, report | Days-to-expiry threshold that marks a cert as expiring |
| `cert_dir` | `/etc/pki/tls/certs` | renew | Directory searched for certs to renew |
| `cert_key_dir` | `/etc/pki/tls/private` | renew | Directory for regenerated private keys |
| `cert_valid_days` | `365` | renew | Validity period of the self-signed renewal |
| `report_dir` | `/tmp` | report | Output location reference for the compliance report |

### 3. Register Job Templates

Create five job templates from `proactive-assessment/playbooks/`. The
`job_template_name` values below must match the AO workflow JSON exactly.

| Job Template Name | Playbook | Runs on |
|-------------------|----------|---------|
| `Cert - Scan Certificates` | `scan_certificates.yml` | `cert-demo-vm` |
| `Cert - Renew Proactive` | `renew_proactive.yml` | `cert-demo-vm` |
| `Cert - Log OK` | `log_ok.yml` | `cert-demo-vm` |
| `Cert - Compliance Report` | `compliance_report.yml` | localhost |
| `Notify Chatroom` | `notify_chatroom.yml` | localhost |

**Credentials:**

- SSH Machine credential on the target-host templates (`Cert - Scan Certificates`,
  `Cert - Renew Proactive`, `Cert - Log OK`)
- No SSH needed on `Cert - Compliance Report` or `Notify Chatroom` — both run on localhost

**Extra vars passed from AO** (enable **Prompt on launch → Extra Variables** on
each template so AO can inject upstream artifacts):

| Template | Extra vars injected by AO |
|----------|---------------------------|
| `Cert - Renew Proactive` | `expiry_window_days` |
| `Cert - Log OK` | `certs_total`, `certs_healthy`, `expiry_window_days` |
| `Cert - Compliance Report` | `certs_total`, `certs_expiring`, `certs_healthy`, `cert_scan_result`, `expiry_window_days`, `notify_host` |
| `Notify Chatroom` | `cert_scan_result`, `certs_total`, `certs_expiring`, `compliance_pct`, `notify_host`, `expiry_window_days` |

### 4. Configure Mattermost

`notify_chatroom.yml` posts a colored attachment via `community.general.mattermost`
(green `#22c55e` when `cert_scan_result == all_ok`, yellow `#eab308` otherwise).

Set these on the `Notify Chatroom` job template (or pass from AO):

| Variable | Purpose |
|----------|---------|
| `api_chat_token` | Mattermost bot API token (required) |
| `mattermost_server` | Host:port (default `44.209.231.244:8065`) |

```bash
# Login (adjust host and credentials)
MM_TOKEN=$(curl -s http://<bastion>:8065/api/v4/users/login \
  -H "Content-Type: application/json" \
  -d '{"login_id":"admin","password":"changeme123"}' -D - | grep "^token:" | awk '{print $2}')

# Create a bot account and token, or use an incoming webhook.
# Store the bot token as api_chat_token on the Notify Chatroom job template.
```

### 5. Import AO Workflow

Import the workflow JSON into automation orchestrator:

| File | Switch routes on | Trigger |
|------|------------------|---------|
| [`ao/proactive-assessment-301.json`](ao/proactive-assessment-301.json) | `cert_scan_result` (`needs_renewal` / `all_ok`) | Scheduled — nightly cron |

**Schedule / trigger.** The workflow defines a `schedule_trigger` named
**"Nightly Cert Scan"** with cron `0 2 * * *` (daily at 02:00). On import, the
trigger fires `Scan Certificates` automatically each night; you can adjust the
cron expression in AO or launch the workflow manually for demos. The edge
`trigger_schedule → scan_certs` wires the schedule to the first job.

**After import, update environment-specific values:**

1. `job_template` / `job_template_name` on each AAP job node (must resolve on your Controller)
2. `credential_id` on each node (use your Controller's credential IDs)
3. `organization_name` — exported as `Default`; change if your JTs live elsewhere
4. Confirm the cron schedule (`0 2 * * *`) suits your demo window

### 6. Configure the Switch Node

The `Route by Scan Result` switch reads the `cert_scan_result` artifact
published by `Scan Certificates` and routes to one of two branches. Both
branches reconverge on the compliance report and notification.

| Switch port | Label | Condition | Target job | Playbook |
|-------------|-------|-----------|------------|----------|
| `case_0` | `needs_renewal` | `${scan_certs.artifacts.cert_scan_result} == 'needs_renewal'` | `Renew Expiring Certs` (`Cert - Renew Proactive`) | `renew_proactive.yml` |
| `case_1` | `all_ok` | `${scan_certs.artifacts.cert_scan_result} == 'all_ok'` | `Log OK — No Action` (`Cert - Log OK`) | `log_ok.yml` |

Downstream (both paths): `Compliance Report` (`Cert - Compliance Report`) →
`Notify Chatroom` (`Notify Chatroom`).

`Scan Certificates` publishes `cert_scan_result` via `set_stats` as
`needs_renewal` when any cert expires within `expiry_window_days`, otherwise
`all_ok`, along with `certs_total`, `certs_expiring`, `certs_healthy`,
`expiry_window_days`, and `notify_host`.

### 7. Test / Verification

Exercise each switch branch by controlling whether a cert falls inside the
expiry window.

**`all_ok` branch (`case_1` → Log OK):**

```bash
# Ensure no scanned cert expires within 30 days, then run the scan.
# Expected: cert_scan_result=all_ok → Log OK — No Action → Compliance Report
#           → green Mattermost notification (compliance ~100%).
```

**`needs_renewal` branch (`case_0` → Renew Expiring Certs):**

```bash
# Seed a soon-to-expire self-signed cert on the target so it lands inside the window:
ssh -i "$CERT_DEMO_SSH_KEY" ec2-user@"$CERT_DEMO_VM_IP" \
  'sudo openssl req -x509 -newkey rsa:2048 -nodes \
     -keyout /etc/pki/tls/private/demo-expiring.key \
     -out /etc/pki/tls/certs/demo-expiring.crt \
     -days 5 -subj "/CN=demo-expiring.local"'

# Run the workflow (or wait for the 02:00 schedule).
# Expected: cert_scan_result=needs_renewal → Renew Expiring Certs
#           (regenerates the cert for cert_valid_days, backs up the original as
#            *.crt.backup) → Compliance Report → yellow Mattermost notification.
```

Verify a renewal took place:

```bash
ssh -i "$CERT_DEMO_SSH_KEY" ec2-user@"$CERT_DEMO_VM_IP" \
  'ls -l /etc/pki/tls/certs/demo-expiring.crt* && \
   openssl x509 -in /etc/pki/tls/certs/demo-expiring.crt -noout -enddate'
```

**Compliance report / notification (both paths):** `Compliance Report` computes
`compliance_pct = certs_healthy / certs_total * 100` and status
`COMPLIANT` (no expiring certs) or `ACTION TAKEN`. `Notify Chatroom` posts the
totals, scan result, renewed count, and compliance percentage to Mattermost.

Confirm on the AO **Input → Schema** for the switch step that
`cert_scan_result` is present as a string artifact after the scan run.

## Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| AAP Gateway | 443 / 8444 | AAP UI and API |
| AO UI | 8080 | automation orchestrator web interface |
| Mattermost | 8065 | Chat notifications |
| SSH | 22 | Ansible connection to demo VM |
