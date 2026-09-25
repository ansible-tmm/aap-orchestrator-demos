# Subscription Management Demo - Full Setup Guide

## Infrastructure Required

| Component | Purpose | How to Provision |
|-----------|---------|------------------|
| AAP 2.7 with AO | Controller + automation orchestrator | `aws-aap-containerized` repo or existing AAP install |
| Demo VM | RHEL 9 EC2 target host for `subscription-manager` check and remediation playbooks | EC2 t3.small in `us-east-1` (or your region) |
| RHSM registration credentials | Register/renew paths call `subscription-manager register` / `attach` — needs an activation key + org ID (or username/password) | Red Hat activation key from the Hybrid Cloud Console, or account credentials |
| Mattermost | Per-status subscription notifications | Container on bastion (or reuse an existing Mattermost instance) |

## Step-by-Step Setup

### 1. Provision Demo VM

```bash
cd ~/work/src/aap-orchestrator-demos

# Create EC2 key pair
aws ec2 create-key-pair --key-name ao-subscription-demo-key \
  --query 'KeyMaterial' --output text --region us-east-1 > ao-subscription-demo-key.pem
chmod 600 ao-subscription-demo-key.pem

# Launch RHEL 9 instance (adjust AMI for your region)
aws ec2 run-instances \
  --image-id ami-0d85f16af633ab171 \
  --instance-type t3.small \
  --key-name ao-subscription-demo-key \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ao-subscription-demo-vm}]' \
  --region us-east-1

# Export connection details for inventory
export SUB_DEMO_VM_IP=<VM_PUBLIC_IP>
export SUB_DEMO_SSH_KEY=$PWD/ao-subscription-demo-key.pem

# Verify SSH
ssh -i "$SUB_DEMO_SSH_KEY" ec2-user@"$SUB_DEMO_VM_IP" 'subscription-manager identity || echo unregistered'
```

The check playbook runs `subscription-manager identity`, `subscription-manager status`, and `subscription-manager list --consumed` on the target and classifies the host into one of four states (see the Switch table below). The register and renew paths mutate subscription state, so the target must be able to reach Red Hat Subscription Management (or Satellite) over HTTPS.

### 2. Configure AAP Project and Inventory

1. **Project** — sync this repo (or `subscription-management/` subtree) from Git.
2. **Inventory** — create a host for the demo VM:

| Host | `ansible_host` | Notes |
|------|----------------|-------|
| `subscription-demo-vm` | VM public IP | `ec2-user`, SSH key credential |

3. **Host / extra variables** (optional overrides used by the playbooks):

| Variable | Default | Purpose | Used by |
|----------|---------|---------|---------|
| `expiry_warn_days` | `30` | Days-remaining boundary for the `expiring` classification | `check_subscription.yml` |
| `test_subscription_status` | *(empty)* | Force a status and skip the live check (see Test section) | `check_subscription.yml` |
| `rhsm_activation_key` | `demo-activation-key` | Activation key used when registering an unregistered host | `register_system.yml` |
| `rhsm_org_id` | `demo-org` | Org ID used during registration | `register_system.yml` |
| `dry_run` | `false` | Reported flag in the Mattermost notification | `notify_chatroom.yml` |

The register and renew playbooks honor Ansible **check mode** (`ansible_check_mode`) — in check mode they only preview the `subscription-manager` commands instead of running them, which is useful for safe demos.

### 3. Register Job Templates

Create six job templates from `subscription-management/playbooks/`. The **Name** column must match the `job_template_name` values in the AO workflow JSON exactly.

| Job Template Name (from AO JSON) | Playbook | Runs on |
|----------------------------------|----------|---------|
| `Subscription - Check Status` | `check_subscription.yml` | `subscription-demo-vm` |
| `Subscription - Log Compliant` | `log_compliant.yml` | `subscription-demo-vm` |
| `Subscription - Notify Expiring` | `notify_expiring.yml` | `subscription-demo-vm` |
| `Subscription - Renew` | `renew_subscription.yml` | `subscription-demo-vm` |
| `Subscription - Register` | `register_system.yml` | `subscription-demo-vm` |
| `Subscription - Notify Chatroom` | `notify_chatroom.yml` | localhost |

**Credentials:**

- SSH Machine credential on the Linux playbooks (`Subscription - Check Status`, `Log Compliant`, `Notify Expiring`, `Renew`, `Register`). These become root via `become: true`.
- RHSM registration data for the `Subscription - Register` template — supply `rhsm_activation_key` and `rhsm_org_id` (as extra vars, a survey, or a custom credential type). For the `Subscription - Renew` template the host must already have an entitlement available for `subscription-manager attach --auto`.
- No SSH needed on `Subscription - Notify Chatroom` — it runs on localhost with `connection: local`.

**Notify template extra vars** — set on `Subscription - Notify Chatroom` or pass from AO:

| Variable | Purpose |
|----------|---------|
| `api_chat_token` | Mattermost bot API token |
| `mattermost_server` | Host:port (default `44.209.231.244:8065`) |

Enable **Prompt on launch → Extra Variables** on the check, remediation, and notify templates so AO can pass artifact values (`subscription_status`, `subscription_expiry`, `subscription_days_remaining`, `notify_host`, `remediation_action`) between nodes.

### 4. Configure Mattermost

```bash
# Login (adjust host and credentials)
MM_TOKEN=$(curl -s http://<bastion>:8065/api/v4/users/login \
  -H "Content-Type: application/json" \
  -d '{"login_id":"admin","password":"changeme123"}' -D - | grep "^token:" | awk '{print $2}')

# Get team and channel IDs
TEAM_ID=$(curl -s http://<bastion>:8065/api/v4/teams \
  -H "Authorization: Bearer ${MM_TOKEN}" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")

# Create a bot account and token, or use an incoming webhook.
# Store the bot token as api_chat_token on the notify job template.
```

`notify_chatroom.yml` sends a color-coded Mattermost attachment via `community.general.mattermost`: green (`#4ade80`) for `registered`, amber (`#fbbf24`) for `expiring`, red (`#f87171`) for `expired`, and bright red (`#ef4444`) for `unregistered`.

### 5. Import AO Workflow

Import the workflow JSON into automation orchestrator:

| File | Switch routes on | Trigger |
|------|------------------|---------|
| [`ao/subscription-management-101.json`](ao/subscription-management-101.json) | `subscription_status` (`registered` / `expiring` / `expired` / `unregistered`) | `schedule_trigger` (Scheduled Compliance Check) |

**After import, update environment-specific values:**

1. `job_template_name` on each node already matches the names in Step 3 — confirm they resolve against your Controller.
2. `credential_id` — the exported JSON carries no credential IDs; assign the SSH Machine credential (and any RHSM/Mattermost credentials) to each node for your Controller.
3. `organization_name` is `Default` on every node — change if you import into a different organization.

### 6. Configure the Switch Node

The switch (`Route by subscription_status`) evaluates `${check_subscription.artifacts.subscription_status}` published by the check playbook via `set_stats`:

| Switch port | Label | Condition | Remediation JT | Follow-up notify |
|-------------|-------|-----------|----------------|------------------|
| `case_0` | `registered` | `subscription_status == 'registered'` | `Subscription - Log Compliant` | `Subscription - Notify Chatroom` (green) |
| `case_1` | `expiring` | `subscription_status == 'expiring'` | `Subscription - Notify Expiring` | `Subscription - Notify Chatroom` (amber) |
| `case_2` | `expired` | `subscription_status == 'expired'` | `Subscription - Renew` | `Subscription - Notify Chatroom` (red) |
| `case_3` | `unregistered` | `subscription_status == 'unregistered'` | `Subscription - Register` | `Subscription - Notify Chatroom` (bright red) |

Each remediation node publishes `remediation_action` and an updated `subscription_status`, which the matching notify node forwards to Mattermost.

### 7. Test / Verification

`check_subscription.yml` accepts `test_subscription_status` as an extra var. When set (non-empty), it skips the live `subscription-manager` calls and forces the classification, so you can exercise every branch without touching real entitlements.

On the **Check Subscription** node in AO, set `extra_vars`:

| Branch | `test_subscription_status` | Expected route |
|--------|----------------------------|----------------|
| Registered / compliant | `registered` | `case_0` → Log Compliant → green notification |
| Expiring soon | `expiring` | `case_1` → Notify Expiring → amber notification |
| Expired | `expired` | `case_2` → Renew → red notification |
| Unregistered | `unregistered` | `case_3` → Register → bright red notification |

Remove `test_subscription_status` (or leave it empty) for a real check. In that mode:

- `unregistered` — `subscription-manager identity` returns non-zero.
- `expired` — days-remaining computes to `< 0`.
- `expiring` — days-remaining `<= expiry_warn_days` (default `30`).
- `registered` — otherwise.

```bash
# Inspect live status on the demo VM
ssh -i "$SUB_DEMO_SSH_KEY" ec2-user@"$SUB_DEMO_VM_IP" \
  'sudo subscription-manager status; sudo subscription-manager list --consumed | grep -i ends'

# Launch the workflow from AO with test_subscription_status=expiring
# Expected: Notify Expiring node runs, amber Mattermost notification with days remaining
```

## Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| AAP Gateway | 443 / 8444 | AAP UI and API |
| AO UI | 8080 | automation orchestrator web interface |
| Mattermost | 8065 | Chat notifications |
| SSH | 22 | Ansible connection to demo VM |
| RHSM / Satellite | 443 | `subscription-manager` register / attach / refresh over HTTPS |
