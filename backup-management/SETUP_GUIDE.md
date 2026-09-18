# Backup Management Demo - Full Setup Guide

This demo checks the most recent backup outcome, publishes `backup_result` as an
AO artifact, and routes to a matching response path via a Switch node:
`success` → verify, `partial` → retry, `failed` → escalate, `skipped` → log.
Every branch ends with a Mattermost notification.

## Infrastructure Required

| Component | Purpose | How to Provision |
|-----------|---------|------------------|
| AAP 2.7 with AO | Controller + automation orchestrator | `aws-aap-containerized` repo or existing AAP install |
| Demo VM | RHEL 9 target host that produces the backup status file and runs the response playbooks | EC2 t3.small in `us-east-1` (or your region) |
| Backup status file | Source of truth read by the check playbook | `/var/log/backup/last_result.txt` on the demo VM (YAML with `result`, `timestamp`, `target_count`, `failed_targets`) |
| Mattermost | Per-outcome remediation notifications | Container on bastion (or reuse an existing Mattermost instance) |

## Step-by-Step Setup

### 1. Provision Demo VM

```bash
cd ~/work/src/aap-orchestrator-demos

# Create EC2 key pair
aws ec2 create-key-pair --key-name ao-backup-demo-key \
  --query 'KeyMaterial' --output text --region us-east-1 > ao-backup-demo-key.pem
chmod 600 ao-backup-demo-key.pem

# Launch RHEL 9 instance (adjust AMI for your region)
aws ec2 run-instances \
  --image-id ami-0d85f16af633ab171 \
  --instance-type t3.small \
  --key-name ao-backup-demo-key \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ao-backup-demo-vm}]' \
  --region us-east-1

# Export connection details for inventory
export BACKUP_DEMO_VM_IP=<VM_PUBLIC_IP>
export BACKUP_DEMO_SSH_KEY=$PWD/ao-backup-demo-key.pem

# Verify SSH
ssh -i "$BACKUP_DEMO_SSH_KEY" ec2-user@"$BACKUP_DEMO_VM_IP" 'hostname'
```

The check playbook reads `/var/log/backup/last_result.txt` (override with the
`backup_status_file` variable). Seed it to control the live outcome:

```bash
# Example: a partial backup outcome
ssh -i "$BACKUP_DEMO_SSH_KEY" ec2-user@"$BACKUP_DEMO_VM_IP" \
  'sudo mkdir -p /var/log/backup && sudo tee /var/log/backup/last_result.txt >/dev/null' <<'EOF'
result: partial
timestamp: 2026-08-24T02:00:00Z
target_count: 5
failed_targets: db02,fileserver
EOF
```

If the status file is missing, the check playbook resolves `backup_result` to
`skipped`.

### 2. Configure AAP Project and Inventory

1. **Project** — sync this repo (or the `backup-management/` subtree) from Git.
2. **Inventory** — create a host and reference it by the name you pass to the
   workflow trigger. The workflow's default trigger `host` is `node1`:

| Host | `ansible_host` | Notes |
|------|----------------|-------|
| `node1` | VM public IP | `ec2-user`, SSH key credential |

3. **Host variables** (optional overrides):

| Variable | Default | Purpose |
|----------|---------|---------|
| `backup_status_file` | `/var/log/backup/last_result.txt` | Status file the check playbook parses |
| `backup_dir` | `/var/backup/latest` | Directory the verify playbook inspects |
| `backup_script` | `/usr/local/bin/run-backup.sh` | Script the retry playbook re-runs for failed targets |

### 3. Register Job Templates

Create six job templates from `backup-management/playbooks/`. The **Name** must
match the `job_template_name` values in the AO workflow JSON exactly:

| Job Template Name (from `ao/backup-management-101.json`) | Playbook | Runs on |
|---------------------------------------------------------|----------|---------|
| `Backup Management - Check Backup` | `check_backup.yml` | target host (`${trigger.host}`) |
| `Backup Management - Verify Backup` | `verify_backup.yml` | target host |
| `Backup Management - Retry Backup` | `retry_backup.yml` | target host |
| `Backup Management - Escalate Backup` | `escalate_backup.yml` | target host |
| `Backup Management - Log Skipped` | `log_skipped.yml` | target host |
| `Backup Management - Notify Chatroom` | `notify_chatroom.yml` | localhost |

**Credentials:**

- SSH Machine credential on the host-facing templates (Check, Verify, Retry,
  Escalate, Log Skipped).
- No SSH needed on Notify Chatroom — the playbook runs on `localhost` with
  `connection: local`.

**Prompt on launch:** enable **Extra Variables** on every template so AO can
pass `${trigger.host}` and upstream artifacts. The check and response playbooks
key their target off `_host`/`limit`, and the workflow forwards artifacts such
as `backup_result`, `backup_timestamp`, `backup_failed_targets`, and
`backup_target_count` between nodes.

### 4. Configure Mattermost Notifications

The `notify_chatroom.yml` playbook posts a colored attachment to Mattermost.
Color is derived from `backup_result`: `success` green (`#4ade80`), `partial`
amber (`#fbbf24`), `failed` red (`#ef4444`), anything else grey (`#666`).

Set these variables (on the `Backup Management - Notify Chatroom` job template or
passed from AO):

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
# Store the bot token as api_chat_token on the notify job template.
```

### 5. Import AO Workflow

Import the workflow JSON into automation orchestrator:

| File | Switch routes on | Trigger input |
|------|------------------|---------------|
| [`ao/backup-management-101.json`](ao/backup-management-101.json) | `backup_result` (`success` / `partial` / `failed` / `skipped`) | `host` (string, default `node1`) |

The check node publishes `backup_result` plus `backup_timestamp`,
`backup_target_count`, `backup_failed_targets`, and `notify_host` for the Switch
and downstream nodes.

**After import, update environment-specific values:**

1. `job_template_name` on each node — must match the templates you created in
   step 3 (already set to `Backup Management - *`; adjust only if you renamed
   them).
2. `credential_id` on every node — the exported JSON uses the placeholder
   `YOUR_AAP_CREDENTIAL_ID`; replace with your Controller credential ID.
3. `organization_name` — exported as `Default`; change if your org differs.
4. The trigger `host` default (`node1`) — set to the inventory host you created.

### 6. Configure the Switch Node

The Switch evaluates `${check_backup.artifacts.backup_result}` against four
conditions, each routing to a response job template and then a notification:

| Switch label | Condition | Response job template | Notify node |
|--------------|-----------|-----------------------|-------------|
| `success` | `backup_result == 'success'` | `Backup Management - Verify Backup` | Notify — Verified (green) |
| `partial` | `backup_result == 'partial'` | `Backup Management - Retry Backup` | Notify — Retried (amber) |
| `failed` | `backup_result == 'failed'` | `Backup Management - Escalate Backup` | Notify — Escalated (red) |
| `skipped` | `backup_result == 'skipped'` | `Backup Management - Log Skipped` | Notify — Skipped (grey) |

Switch ports map to edges `case_0` → verify, `case_1` → retry, `case_2` →
escalate, `case_3` → log skipped.

After a check run, confirm the Switch step's **Input → Schema** shows
`backup_result` as a `string` matching one of the four labels above (the check
playbook trims and lowercases the value before publishing).

### 7. Test / Verification

`check_backup.yml` accepts `test_backup_result` as an extra var. When set, it
skips the live status-file read and simulates the outcome for routing.

On the **Check Backup Result** node in AO (or on the job template), set
`extra_vars` to exercise each branch:

| Branch | `test_backup_result` | Expected route |
|--------|----------------------|----------------|
| Verify | `success` | Verify Backup → green notification |
| Retry | `partial` | Retry Partial → amber notification |
| Escalate | `failed` | Escalate → red notification |
| Log Skipped | `skipped` | Log Skipped → grey notification |

```bash
# Live path (no test var): seed the status file, then launch the workflow.
# result: success  -> Verify Backup   -> green "Verify Backup" notification
# result: partial  -> Retry Partial   -> amber notification with failed targets
# result: failed   -> Escalate        -> red notification with escalation summary
# (missing file)   -> Log Skipped      -> grey notification

# Confirm the seeded outcome on the VM before launching:
ssh -i "$BACKUP_DEMO_SSH_KEY" ec2-user@"$BACKUP_DEMO_VM_IP" \
  'cat /var/log/backup/last_result.txt 2>/dev/null || echo "no status file -> skipped"'
```

Remove `test_backup_result` (or leave it empty) for a real backup-status check.

## Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| AAP Gateway | 443 / 8444 | AAP UI and API |
| AO UI | 8080 | automation orchestrator web interface |
| Mattermost | 8065 | Chat notifications |
| SSH | 22 | Ansible connection to demo VM |
