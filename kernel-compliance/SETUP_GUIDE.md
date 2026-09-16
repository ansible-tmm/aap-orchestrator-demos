# Kernel Compliance Demo - Full Setup Guide

## Infrastructure Required

| Component | Purpose | How to Provision |
|-----------|---------|------------------|
| AAP 2.7 with AO | Controller + automation orchestrator | `aws-aap-containerized` repo or existing AAP install |
| Demo VM | RHEL 8/9 target host for the kernel scan and remediation playbooks | EC2 t3.small in `us-east-1` (or your region) |
| SSH Machine credential | Privilege escalation (`become: true`) for kernel scan, reboot scheduling, and update playbooks | Machine credential on the Linux job templates |
| Mattermost | Compliance-state remediation notifications | Container on bastion (or reuse an existing Mattermost instance) |

## Step-by-Step Setup

### 1. Provision Demo VM

```bash
cd ~/work/src/aap-orchestrator-demos

# Create EC2 key pair
aws ec2 create-key-pair --key-name ao-kernel-demo-key \
  --query 'KeyMaterial' --output text --region us-east-1 > ao-kernel-demo-key.pem
chmod 600 ao-kernel-demo-key.pem

# Launch RHEL instance (adjust AMI for your region)
aws ec2 run-instances \
  --image-id ami-0d85f16af633ab171 \
  --instance-type t3.small \
  --key-name ao-kernel-demo-key \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ao-kernel-demo-vm}]' \
  --region us-east-1

# Export connection details for inventory
export KERNEL_DEMO_VM_IP=<VM_PUBLIC_IP>
export KERNEL_DEMO_SSH_KEY=$PWD/ao-kernel-demo-key.pem

# Verify SSH and that kernel tooling is present
ssh -i "$KERNEL_DEMO_SSH_KEY" ec2-user@"$KERNEL_DEMO_VM_IP" \
  'uname -r; sudo which needs-restarting || sudo dnf install -y yum-utils'
```

The scan playbook (`check_kernel.yml`) uses `uname -r`, `rpm -qa kernel`, and `needs-restarting -r` (from `yum-utils`) to classify state, so ensure `yum-utils` is installed on the target for a live scan.

### 2. Configure AAP Project and Inventory

1. **Project** — sync this repo (or the `kernel-compliance/` subtree) from Git.
2. **Inventory** — create a host for the demo VM:

| Host | `ansible_host` | Notes |
|------|----------------|-------|
| `kernel-demo-vm` | VM public IP | `ec2-user`, SSH key credential, `become: true` |

3. **Host / extra variables** (optional overrides):

| Variable | Default | Purpose |
|----------|---------|---------|
| `_host` | `all` | Limit target host pattern for each play |
| `eol_kernels` | `['3.10', '4.18.0-80', '4.18.0-147']` | Version fragments treated as end-of-life by the scan |
| `maintenance_window_hours` | `4` | Window recorded by the schedule-reboot playbook |
| `test_kernel_compliance` | (empty) | Force a compliance state for demos (see Test / Verification) |

### 3. Register Job Templates

Create six job templates from `kernel-compliance/playbooks/`. The **Name** column must match the `job_template_name` values in the AO workflow JSON exactly.

| Job Template Name (in AO JSON) | Playbook | Runs on |
|--------------------------------|----------|---------|
| `Kernel - Check Compliance` | `check_kernel.yml` | `kernel-demo-vm` |
| `Kernel - Log Compliant` | `log_compliant.yml` | `kernel-demo-vm` |
| `Kernel - Schedule Reboot` | `schedule_reboot.yml` | `kernel-demo-vm` |
| `Kernel - Apply Update` | `apply_kernel_update.yml` | `kernel-demo-vm` |
| `Kernel - Flag EOL Migration` | `flag_eol_migration.yml` | `kernel-demo-vm` |
| `Kernel - Notify Chatroom` | `notify_chatroom.yml` | localhost |

**Credentials:**

- SSH Machine credential on the Linux templates: `Kernel - Check Compliance`, `Kernel - Log Compliant`, `Kernel - Schedule Reboot`, `Kernel - Apply Update`, `Kernel - Flag EOL Migration` (the scan, reboot, and update plays use `become: true`).
- No SSH needed on `Kernel - Notify Chatroom` — it runs on `localhost` with `connection: local`.

**Prompt on launch — Extra Variables:** enable **Prompt on launch → Extra Variables** on every template above so AO can pass artifacts (`kernel_compliance`, `kernel_running`, `kernel_latest`, `remediation_action`, `notify_host`) between nodes.

### 4. Configure Mattermost Notifications

The `notify_chatroom.yml` playbook posts a color-coded attachment to Mattermost using `community.general.mattermost`. It needs two variables:

| Variable | Purpose |
|----------|---------|
| `api_chat_token` | Mattermost bot API token (required) |
| `mattermost_server` | Host:port (default `44.209.231.244:8065`) |

Set these on the `Kernel - Notify Chatroom` job template (or pass from AO). Attachment color is chosen from the compliance state:

| `kernel_compliance` | Color |
|---------------------|-------|
| `compliant` | `#4ade80` (green) |
| `reboot_required` | `#fbbf24` (amber) |
| `drift` | `#fb923c` (orange) |
| `eol` | `#ef4444` (red) |
| any other value | `#888888` (grey) |

```bash
# Login (adjust host and credentials)
MM_TOKEN=$(curl -s http://<bastion>:8065/api/v4/users/login \
  -H "Content-Type: application/json" \
  -d '{"login_id":"admin","password":"changeme123"}' -D - | grep "^token:" | awk '{print $2}')

# Create a bot account and token, or use an incoming webhook.
# Store the bot token as api_chat_token on the Kernel - Notify Chatroom job template.
```

## Import AO Workflow

Import the workflow JSON into automation orchestrator:

| File | Trigger | Switch routes on |
|------|---------|------------------|
| [`ao/kernel-compliance-101.json`](ao/kernel-compliance-101.json) | Scheduled kernel scan (`schedule_trigger`, no input schema) | `check_kernel.artifacts.kernel_compliance` |

The trigger is a schedule trigger with empty parameters (no `input_schema`); the workflow starts on the `Check Kernel Compliance` job node.

**After import, update environment-specific values for your Controller:**

1. `job_template_name` on each node already matches the table in Step 3 — confirm the templates exist with those exact names in the `Default` organization (each node sets `organization_name: "Default"`).
2. Add / update the `credential_id` on each job node to point at your Controller's credentials (the exported JSON intentionally omits credential IDs for a clean import).
3. Confirm each node's `extra_vars` reference the upstream artifacts from `check_kernel` and the matching remediation node (see the Switch table below).

## Configure the Switch Node

The switch step `Route by kernel_compliance` evaluates `${check_kernel.artifacts.kernel_compliance}` against four conditions (ports `case_0`–`case_3`):

| Switch port | Label | Condition | Remediation JT | Downstream notify |
|-------------|-------|-----------|----------------|-------------------|
| `case_0` | `compliant` | `${check_kernel.artifacts.kernel_compliance} == 'compliant'` | `Kernel - Log Compliant` | Notify — Compliant |
| `case_1` | `reboot_required` | `${check_kernel.artifacts.kernel_compliance} == 'reboot_required'` | `Kernel - Schedule Reboot` | Notify — Reboot Scheduled |
| `case_2` | `drift` | `${check_kernel.artifacts.kernel_compliance} == 'drift'` | `Kernel - Apply Update` | Notify — Kernel Updated |
| `case_3` | `eol` | `${check_kernel.artifacts.kernel_compliance} == 'eol'` | `Kernel - Flag EOL Migration` | Notify — EOL Flagged |

Each remediation node forwards `kernel_compliance`, `kernel_running`, and (except EOL) `kernel_latest` to its notify node, plus `remediation_action` published by the remediation playbook (`Log Compliant`, `Schedule Reboot`, `Apply Kernel Update`, `Flag EOL Migration`) and `notify_host` from the scan.

## Test / Verification

The scan playbook `check_kernel.yml` accepts a `test_kernel_compliance` extra var. When set, it **skips the live check** (`uname`, `rpm`, `needs-restarting`) and publishes the supplied value straight to the `kernel_compliance` artifact, so you can exercise every switch branch deterministically.

On the `Check Kernel Compliance` node in AO, set `extra_vars`:

| Branch | `test_kernel_compliance` | Expected route | Expected notification |
|--------|--------------------------|----------------|-----------------------|
| Compliant | `compliant` | `case_0` → Log Compliant | green attachment |
| Reboot required | `reboot_required` | `case_1` → Schedule Reboot | amber attachment |
| Drift | `drift` | `case_2` → Apply Kernel Update | orange attachment |
| EOL | `eol` | `case_3` → Flag EOL Migration | red attachment |

Remove `test_kernel_compliance` (or leave it empty) to run a real scan, which classifies as `eol` (running an EOL kernel), then `reboot_required` (`needs-restarting -r` returns non-zero), then `drift` (running kernel != latest installed), else `compliant`.

```bash
# Live classification preview on the demo VM
ssh -i "$KERNEL_DEMO_SSH_KEY" ec2-user@"$KERNEL_DEMO_VM_IP" '
  echo "running:  $(uname -r)"
  echo "latest:   $(rpm -qa kernel --queryformat "%{VERSION}-%{RELEASE}.%{ARCH}\n" | sort -V | tail -1)"
  sudo needs-restarting -r; echo "needs-restarting rc=$?"
'

# Launch workflow from AO with test_kernel_compliance=drift
# Expected: case_2 → Apply Kernel Update → orange Mattermost notification
```

To simulate `reboot_required` or `drift` live: install an older kernel then boot into it (`grubby --set-default`, reboot) so the running kernel lags the latest installed, or run `dnf update kernel` without rebooting.

## Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| AAP Gateway | 443 / 8444 | AAP UI and API |
| AO UI | 8080 | automation orchestrator web interface |
| Mattermost | 8065 | Chat notifications |
| SSH | 22 | Ansible connection to demo VM |
