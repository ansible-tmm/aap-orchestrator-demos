# Certificate Expiry Threshold Routing Demo - Full Setup Guide

Rule-based certificate expiry handling. The workflow checks a certificate's
remaining lifetime, classifies it into a `cert_status` tier from the days
remaining, and routes to the matching remediation path — no LLM required.

## Infrastructure Required

| Component | Purpose | How to Provision |
|-----------|---------|------------------|
| AAP 2.7 with AO | Controller + automation orchestrator | `aws-aap-containerized` repo or existing AAP install |
| Demo VM | RHEL 9 EC2 target host holding the certificate to check and renew | EC2 t3.small in `us-east-1` (or your region) |
| Certificate on target | The cert whose expiry is evaluated (default `/etc/pki/tls/certs/server.crt`) | Existing PKI cert, or a self-signed cert placed for the demo |
| `community.crypto` collection | Key/CSR/cert generation on the renew and emergency paths | Ship in the execution environment |
| Mattermost | Tier-specific expiry notifications | Container on bastion (or reuse an existing Mattermost instance) |

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
ssh -i "$CERT_DEMO_SSH_KEY" ec2-user@"$CERT_DEMO_VM_IP" 'hostname'
```

Place (or confirm) a certificate at the path the check playbook reads. The
default is `/etc/pki/tls/certs/server.crt` with its key at
`/etc/pki/tls/private/server.key`. For a quick demo cert:

```bash
ssh -i "$CERT_DEMO_SSH_KEY" ec2-user@"$CERT_DEMO_VM_IP" \
  'sudo openssl req -x509 -newkey rsa:2048 -nodes \
     -keyout /etc/pki/tls/private/server.key \
     -out /etc/pki/tls/certs/server.crt \
     -days 45 -subj "/CN=demo.example.com"'
```

Choosing `-days 45` here lands the cert in the `plan` tier for a live check.

### 2. Configure AAP Project and Inventory

1. **Project** — sync this repo (or `cert-expiry-switch/` subtree) from Git.
2. **Inventory** — create a host for the target VM:

| Host | `ansible_host` | Notes |
|------|----------------|-------|
| `cert-demo-vm` | VM public IP | `ec2-user`, SSH key credential |

3. **Host / extra variables** (optional overrides — defaults come from the playbooks):

| Variable | Default | Purpose |
|----------|---------|---------|
| `cert_path` | `/etc/pki/tls/certs/server.crt` | Certificate file to check / renew |
| `cert_key_path` | `/etc/pki/tls/private/server.key` | Private key path (renew / emergency) |
| `cert_domain` | `inventory_hostname` | Domain / CN for CSR and TLS validation |
| `healthy_days` | `60` | Above this → `healthy` |
| `plan_days` | `30` | Above this (≤ `healthy_days`) → `plan` |
| `renew_days` | `7` | Above this (≤ `plan_days`) → `renew`; at or below → `emergency` |
| `cert_valid_days` | `365` | Lifetime of the renewed certificate |
| `cert_key_size` | `2048` | Key size for the renewed certificate |
| `validate_port` | `443` | Local port for the TLS handshake check |

### 3. Register Job Templates

Create seven job templates from `cert-expiry-switch/playbooks/`. The **Name**
column must match the `job_template_name` values in the AO workflow JSON exactly.

| Job Template Name | Playbook | Runs on |
|-------------------|----------|---------|
| `Cert - Check Expiry` | `check_cert_expiry.yml` | `cert-demo-vm` |
| `Cert - Skip Healthy` | `skip_healthy.yml` | `cert-demo-vm` |
| `Cert - Open Change Request` | `open_change_request.yml` | `cert-demo-vm` |
| `Cert - Renew` | `renew_cert.yml` | `cert-demo-vm` |
| `Cert - Emergency Renew` | `emergency_renew.yml` | `cert-demo-vm` |
| `Cert - Validate TLS` | `validate_tls.yml` | `cert-demo-vm` |
| `Cert - Notify Chatroom` | `notify_chatroom.yml` | localhost |

`Cert - Validate TLS` is reused by both the renew and emergency branches, and
`Cert - Notify Chatroom` is reused by all four notify nodes — register each once.

**Credentials:**

- SSH Machine credential on all Linux playbooks (Check Expiry, Skip Healthy,
  Open Change Request, Renew, Emergency Renew, Validate TLS)
- No SSH needed on notify (`Cert - Notify Chatroom`) — runs on localhost
- Ensure the execution environment provides the `community.crypto` collection
  (Renew / Emergency Renew) and `community.general` (Notify Chatroom)

**Prompt on launch — Extra Variables:** enable on every template so AO can pass
the check node's published artifacts (`cert_status`, `days_remaining`,
`cert_expiry_date`, `cert_domain`, `cert_path`, `notify_host`) downstream.

**Notify template extra vars** — set on `Cert - Notify Chatroom` or pass from AO:

| Variable | Purpose |
|----------|---------|
| `api_chat_token` | Mattermost bot API token |
| `mattermost_server` | Host:port (default `44.209.231.244:8065`) |

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

# Create bot account and token, or use an incoming webhook
# Store the bot token as api_chat_token on the Cert - Notify Chatroom job template
```

The notify playbook color-codes the Mattermost attachment by `cert_status`:
green (`healthy`), blue (`plan`), amber (`renew`/`renewed`), red (`emergency`).

### 5. Import AO Workflow

Import the workflow JSON into automation orchestrator:

| File | Switch routes on | Trigger inputs |
|------|------------------|----------------|
| [`ao/cert-expiry-switch-101.json`](ao/cert-expiry-switch-101.json) | `cert_status` (`healthy` / `plan` / `renew` / `emergency`) | `cert_path`, `cert_domain` |

The `Manual or Schedule` trigger exposes an `input_schema` with:

| Input | Default | Description |
|-------|---------|-------------|
| `cert_path` | `/etc/pki/tls/certs/server.crt` | Path to the certificate file to check |
| `cert_domain` | `` (empty) | Domain name for TLS validation |

These flow into `Cert - Check Expiry` as `extra_vars`. The check node publishes
`cert_status`, `days_remaining`, `cert_expiry_date`, `cert_path`, `cert_domain`,
and `notify_host` via `set_stats`, which the switch and every downstream node
consume as `${check_cert_expiry.artifacts.*}`.

**After import, update environment-specific values:**

1. `credential_id` on each AAP job node — the exported JSON ships without
   credential IDs; assign your Controller's Machine (and any EE) credentials
2. Confirm each `job_template` / `job_template_name` resolves to the templates
   you registered in Step 3 on your Controller (`organization_name` is `Default`)
3. For a scripted test, set `test_cert_status` / `test_days_remaining` on the
   check node (see Step 7) — remove them for a live certificate check

### 6. Configure the Switch Node

The `Route by cert_status` switch has four conditions, matched in order against
the `cert_status` artifact from `Cert - Check Expiry`:

| Switch port | Condition | Days remaining | Remediation path | Notify color |
|-------------|-----------|----------------|------------------|--------------|
| `case_0` — `healthy` | `cert_status == 'healthy'` | > 60 | `Cert - Skip Healthy` → Notify | green |
| `case_1` — `plan` | `cert_status == 'plan'` | 30–60 | `Cert - Open Change Request` → Notify | blue |
| `case_2` — `renew` | `cert_status == 'renew'` | 7–30 | `Cert - Renew` → `Cert - Validate TLS` → Notify | amber |
| `case_3` — `emergency` | `cert_status == 'emergency'` | < 7 | `Cert - Emergency Renew` → `Cert - Validate TLS` → Notify | red |

Only the `renew` and `emergency` branches run `Cert - Validate TLS` (they
regenerate the cert); `healthy` and `plan` go straight to notify. The day-range
boundaries come from `healthy_days` (60), `plan_days` (30), and `renew_days` (7)
in `check_cert_expiry.yml`.

### 7. Test Branches Without Waiting for Real Expiry

`check_cert_expiry.yml` accepts `test_cert_status` (and optional
`test_days_remaining`) as extra vars. When `test_cert_status` is set, the
playbook skips the live `openssl` check and publishes the simulated status
straight to the switch.

On the **Check Cert Expiry** node in AO, set `extra_vars`:

| Branch | `test_cert_status` | `test_days_remaining` (optional) |
|--------|--------------------|----------------------------------|
| Skip Healthy (`case_0`) | `healthy` | `90` |
| Open Change Request (`case_1`) | `plan` | `45` |
| Renew + Validate (`case_2`) | `renew` | `20` |
| Emergency Renew + Validate (`case_3`) | `emergency` | `3` |

Remove `test_cert_status` for a real check — the tier is then computed from the
actual certificate's `openssl x509 -enddate` and the day thresholds. To drive a
live branch, provision the cert with a matching `-days` value (Step 1): e.g.
`-days 45` → `plan`, `-days 20` → `renew`, `-days 3` → `emergency`.

Run renew / emergency job templates in **check mode** first (all destructive
key/cert generation tasks are gated on `not ansible_check_mode`) to preview
without regenerating keys.

## Verification

```bash
# Live cert status on the demo VM (mirrors the check playbook logic)
ssh -i "$CERT_DEMO_SSH_KEY" ec2-user@"$CERT_DEMO_VM_IP" \
  'sudo openssl x509 -in /etc/pki/tls/certs/server.crt -noout -enddate'

# Launch workflow from AO UI with test_cert_status=healthy
# Expected: Skip Healthy → green Mattermost notification, no cert change

# Launch with test_cert_status=plan
# Expected: Open Change Request → /var/tmp/cert-change-request marker, blue notification

# Launch with test_cert_status=renew
# Expected: Renew → Validate TLS (validation_passed=True) → amber notification

# Launch with test_cert_status=emergency
# Expected: Emergency Renew → Validate TLS → red notification
```

On the `renew` and `emergency` branches, `Cert - Validate TLS` performs a local
`openssl s_client` handshake on `validate_port` (default 443) and publishes
`validation_passed`, which the notify node surfaces in the Mattermost message.

## Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| AAP Gateway | 443 / 8444 | AAP UI and API |
| AO UI | 8080 | automation orchestrator web interface |
| Mattermost | 8065 | Chat notifications |
| TLS validation | 443 | `openssl s_client` handshake check (`validate_port`) |
| SSH | 22 | Ansible connection to demo VM |
