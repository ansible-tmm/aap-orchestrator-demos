# Patch Management Demo - Full Setup Guide

## Infrastructure Required

| Component | Purpose | How to Provision |
|-----------|---------|------------------|
| AAP 2.7 with AO | Controller + automation orchestrator | `aws-aap-containerized` repo or existing AAP install |
| Demo VM | RHEL 9 target host for patch assessment and remediation playbooks | EC2 t3.small in `us-east-1` (or your region) |
| Mattermost | Severity-tiered patch notifications | Container on bastion (or reuse an existing Mattermost instance) |

The remediation playbooks (`remediate_patch_now.yml`, `remediate_schedule_change.yml`, `remediate_weekly_batch.yml`, `remediate_report_compliant.yml`) run `dnf` / `needs-restarting` on the RHEL target. `notify_chatroom.yml` runs on localhost and only needs network reach to Mattermost.

## Step-by-Step Setup

### 1. Provision Demo VM

```bash
cd ~/work/src/aap-orchestrator-demos

# Create EC2 key pair
aws ec2 create-key-pair --key-name ao-patch-demo-key \
  --query 'KeyMaterial' --output text --region us-east-1 > ao-patch-demo-key.pem
chmod 600 ao-patch-demo-key.pem

# Launch RHEL 9 instance (adjust AMI for your region)
aws ec2 run-instances \
  --image-id ami-0d85f16af633ab171 \
  --instance-type t3.small \
  --key-name ao-patch-demo-key \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ao-patch-demo-vm}]' \
  --region us-east-1

# Export connection details for inventory
export PATCH_DEMO_VM_IP=<VM_PUBLIC_IP>
export PATCH_DEMO_SSH_KEY=$PWD/ao-patch-demo-key.pem

# Verify SSH and dnf updateinfo access
ssh -i "$PATCH_DEMO_SSH_KEY" ec2-user@"$PATCH_DEMO_VM_IP" 'sudo dnf updateinfo --summary'
```

`check_patches.yml` parses `dnf updateinfo --summary` for `Critical`, `Important`, and `Moderate` advisory counts. The remediation playbooks require `sudo` (they run with `become: true`), so a RHEL 9 subscription/repos are needed for a live scan. Use the test variable in the [Test / Verification](#test--verification) section to exercise every branch without pending advisories.

### 2. Configure AAP Project and Inventory

1. **Project** — sync this repo (or the `patch-management/` subtree) from Git.
2. **Inventory** — create a host that matches the trigger `host` default of `node1`:

| Host | `ansible_host` | Notes |
|------|----------------|-------|
| `node1` | VM public IP | `ec2-user`, SSH key credential |

The AO trigger passes `host` (default `node1`) into each job template's `limit`, and the check/remediation playbooks target `{{ _host | default('all') }}`. Keep the inventory host name aligned with the trigger `host` value.

### 3. Register Job Templates

Create six job templates from `patch-management/playbooks/`. The names must match the `job_template_name` values in the AO workflow JSON exactly:

| `job_template_name` (from AO JSON) | Playbook | Runs on |
|------------------------------------|----------|---------|
| `Patch Management - Check Patches` | `check_patches.yml` | `node1` |
| `Patch Management - Patch Now` | `remediate_patch_now.yml` | `node1` |
| `Patch Management - Schedule Change` | `remediate_schedule_change.yml` | `node1` |
| `Patch Management - Weekly Batch` | `remediate_weekly_batch.yml` | `node1` |
| `Patch Management - Report Compliant` | `remediate_report_compliant.yml` | `node1` |
| `Patch Management - Notify Chatroom` | `notify_chatroom.yml` | localhost |

**Credentials:**

- SSH Machine credential on all Linux templates (Check Patches, Patch Now, Schedule Change, Weekly Batch, Report Compliant).
- No SSH needed on `Patch Management - Notify Chatroom` — it runs on localhost with `connection: local`.

**Prompt on launch — Extra Variables:** enable this on every template so AO can pass artifacts downstream. The workflow feeds `highest_severity` and the `advisory_count_*` values from the check node into the remediation and notify nodes, plus `remediation_action`, `packages_updated`, `reboot_required`, and `notify_host` into the notify node.

### 4. Configure Mattermost Notifications

`notify_chatroom.yml` posts a color-coded attachment to Mattermost. Colors are keyed to `highest_severity`:

| `highest_severity` | Attachment color |
|--------------------|------------------|
| `critical` | `#ef4444` (red) |
| `important` | `#f97316` (orange) |
| `moderate` | `#fbbf24` (yellow) |
| anything else (e.g. `none`) | `#4ade80` (green) |

Set these variables on the `Patch Management - Notify Chatroom` job template (or pass them from AO):

| Variable | Purpose |
|----------|---------|
| `api_chat_token` | Mattermost bot API token (required) |
| `mattermost_server` | Host:port (default `44.209.231.244:8065`) |

```bash
# Login (adjust host and credentials)
MM_TOKEN=$(curl -s http://<bastion>:8065/api/v4/users/login \
  -H "Content-Type: application/json" \
  -d '{"login_id":"admin","password":"changeme123"}' -D - | grep "^token:" | awk '{print $2}')

# Create a bot account and token, then store the bot token as api_chat_token
# on the Patch Management - Notify Chatroom job template
```

## Import AO Workflow

Import the workflow JSON into automation orchestrator:

| File | Switch routes on |
|------|------------------|
| [`ao/patch-management-101.json`](ao/patch-management-101.json) | `highest_severity` (`critical` / `important` / `moderate` / `none`) |

The check node publishes `highest_severity` plus `advisory_count_critical`, `advisory_count_important`, `advisory_count_moderate`, and `notify_host` via `set_stats` for the switch and downstream nodes.

**After import, update environment-specific values** — the exported JSON ships with placeholders:

1. `credential_id` on every `aap_job_template` node — replace `YOUR_AAP_CREDENTIAL_ID` with your Controller credential ID.
2. `job_template_name` on each node — confirm the names match the templates you created in Step 3 for your Controller.
3. `organization_name` — set to your organization (exported default is `Default`).
4. The trigger `host` input — exported default is `node1`; change it to match your inventory host.

## Configure the Switch Node

The switch (`route_switch`) reads `${check_patches.artifacts.highest_severity}` and routes to one remediation branch, each followed by a Mattermost notify:

| Switch label | Condition (from AO JSON) | Port | Remediation JT | Playbook | Follow-up notify node |
|--------------|--------------------------|------|----------------|----------|-----------------------|
| `critical` | `${check_patches.artifacts.highest_severity} == 'critical'` | `case_0` | `Patch Management - Patch Now` | `remediate_patch_now.yml` (apply security updates now, check reboot) | Notify — Patched |
| `important` | `${check_patches.artifacts.highest_severity} == 'important'` | `case_1` | `Patch Management - Schedule Change` | `remediate_schedule_change.yml` (list advisories, schedule window) | Notify — Scheduled |
| `moderate` | `${check_patches.artifacts.highest_severity} == 'moderate'` | `case_2` | `Patch Management - Weekly Batch` | `remediate_weekly_batch.yml` (write batch manifest) | Notify — Batched |
| `none` | `${check_patches.artifacts.highest_severity} == 'none'` | `case_3` | `Patch Management - Report Compliant` | `remediate_report_compliant.yml` (log compliant, exit) | Notify — Compliant |

The `critical` branch additionally passes `advisory_count_critical` as an extra var, `important` passes `advisory_count_important`, and `moderate` passes `advisory_count_moderate`; all branches pass `highest_severity`.

## Test / Verification

`check_patches.yml` accepts a `test_highest_severity` extra var. When set, it skips the live `dnf updateinfo` scan and publishes the supplied value directly, letting you drive any switch branch deterministically.

On the **Patch Assessment** (`check_patches`) node in AO, set `extra_vars`:

| Branch | `test_highest_severity` | Expected remediation | Expected notify color |
|--------|-------------------------|----------------------|-----------------------|
| Patch Now | `critical` | `remediate_patch_now.yml` | red (`#ef4444`) |
| Schedule Change | `important` | `remediate_schedule_change.yml` | orange (`#f97316`) |
| Weekly Batch | `moderate` | `remediate_weekly_batch.yml` | yellow (`#fbbf24`) |
| Report Compliant | `none` | `remediate_report_compliant.yml` | green (`#4ade80`) |

```bash
# Live scan on the demo VM (no test override) — see the real highest severity
ssh -i "$PATCH_DEMO_SSH_KEY" ec2-user@"$PATCH_DEMO_VM_IP" 'sudo dnf updateinfo --summary'

# In AO, launch the workflow with test_highest_severity=critical on the check node.
# Expected: Patch Now -> red "Patch Management - Patch Now" Mattermost notification.

# Launch with test_highest_severity=important
# Expected: Schedule Change -> orange notification with the advisory count.

# Launch with test_highest_severity=moderate
# Expected: Weekly Batch -> yellow notification; batch manifest under /var/log/patch-batch/.

# Launch with test_highest_severity=none
# Expected: Report Compliant -> green notification.
```

Remove `test_highest_severity` (or leave it empty) for a real advisory scan; the check playbook then parses `dnf updateinfo --summary` and derives `highest_severity` from the critical/important/moderate counts, defaulting to `none` when there are no advisories.

## Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| AAP Gateway | 443 / 8444 | AAP UI and API |
| AO UI | 8080 | automation orchestrator web interface |
| Mattermost | 8065 | Chat notifications |
| SSH | 22 | Ansible connection to demo VM |
