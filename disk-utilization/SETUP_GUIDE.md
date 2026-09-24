# Disk Utilization Demo - Full Setup Guide

## Infrastructure Required

| Component | Purpose | How to Provision |
|-----------|---------|------------------|
| AAP 2.7 with AO | Controller + automation orchestrator | `aws-aap-containerized` repo or existing AAP install |
| Demo VM | RHEL 9 EC2 target host for disk check and remediate playbooks | EC2 t3.small in `us-east-1` (or your region) |
| AWS credentials | EBS volume modification on the expand path | IAM role on the EC2 instance, or Machine credential on the expand job template |
| Mattermost | Tier-specific remediation notifications | Container on bastion (or reuse an existing Mattermost instance) |

## Step-by-Step Setup

### 1. Provision Demo VM

```bash
cd ~/work/src/aap-orchestrator-demos

# Create EC2 key pair
aws ec2 create-key-pair --key-name ao-disk-demo-key \
  --query 'KeyMaterial' --output text --region us-east-1 > ao-disk-demo-key.pem
chmod 600 ao-disk-demo-key.pem

# Launch RHEL 9 instance (adjust AMI for your region)
aws ec2 run-instances \
  --image-id ami-0d85f16af633ab171 \
  --instance-type t3.small \
  --key-name ao-disk-demo-key \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ao-disk-demo-vm}]' \
  --region us-east-1

# Export connection details for inventory
export DISK_DEMO_VM_IP=<VM_PUBLIC_IP>
export DISK_DEMO_SSH_KEY=$PWD/ao-disk-demo-key.pem

# Verify SSH
ssh -i "$DISK_DEMO_SSH_KEY" ec2-user@"$DISK_DEMO_VM_IP" 'df -h /'
```

Target layout (RHEL 9 on EC2): GPT disk `/dev/nvme0n1`, root partition `nvme0n1p4`, XFS on `/`.

For the **expand** path, attach an IAM instance profile with `ec2:ModifyVolume`, `ec2:DescribeVolumes`, and `ec2:DescribeInstances`, or provide equivalent AWS credentials to the execution environment.

### 2. Configure AAP Project and Inventory

1. **Project** — sync this repo (or `disk-utilization/` subtree) from Git.
2. **Inventory** — create a host matching `disk-utilization/inventory/hosts.yml`:

| Host | `ansible_host` | Notes |
|------|----------------|-------|
| `disk-demo-vm` | VM public IP | `ec2-user`, SSH key credential |

3. **Host variables** (optional overrides):

| Variable | Default | Purpose |
|----------|---------|---------|
| `ec2_instance_id` | auto-discovered | Skip discovery if you set it explicitly |
| `disk_mount` | `/` | Filesystem to monitor |
| `disk_warn_threshold` | `80` | Warn tier boundary |
| `disk_critical_threshold` | `95` | Critical tier boundary |
| `disk_expand_gb` | `5` | GiB to add on expand path |
| `aws_region` | `us-east-1` | Region for EBS API calls |

`ec2_instance_id` is optional — the expand playbook auto-discovers the instance via EC2 metadata or AWS API IP lookup.

### 3. Register Job Templates

Create six job templates from `disk-utilization/playbooks/`:

| JT ID (nostromo) | Name | Playbook | Runs on |
|------------------|------|----------|---------|
| 115 | Disk Utilization Check | `check_disk.yml` | `disk-demo-vm` |
| 116 | Linux - Remediate - Disk Cleanup | `remediate_disk_cleanup.yml` | `disk-demo-vm` |
| 117 | Notify Chatroom | `notify_chatroom.yml` | localhost |
| 118 | Linux - Remediate - Continue | `remediate_disk_continue.yml` | `disk-demo-vm` |
| 119 | Linux - Remediate - Disk Expand | `remediate_disk_expand.yml` | localhost + `disk-demo-vm` |
| 120 | Disk Utilization - Fallback | `remediate_disk_fallback.yml` | `disk-demo-vm` |

**Credentials:**

- SSH Machine credential on Linux playbooks (115, 116, 118, 119 host play, 120)
- AWS credential on the expand template (119) if not using an instance profile
- No SSH needed on notify (117) — runs on localhost

**Notify template extra vars** — set on JT 117 or pass from AO:

| Variable | Purpose |
|----------|---------|
| `api_chat_token` | Mattermost bot API token |
| `mattermost_server` | Host:port (default `44.209.231.244:8065`) |

Enable **Prompt on launch → Extra Variables** on JT 117 so AO can pass artifact values from upstream remediate steps.

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
# Store the bot token as api_chat_token on the notify job template
```

### 5. Import AO Workflow

Import one workflow JSON into automation orchestrator:

| File | Switch routes on | Use when |
|------|------------------|----------|
| [`ao/disk-demo-101.json`](ao/disk-demo-101.json) | `disk_use_percent` (numeric comparisons) | Demonstrating AO threshold expressions |
| [`ao/disk-demo-tier-switch.json`](ao/disk-demo-tier-switch.json) | `disk_tier` (`ok` / `warn` / `critical`) | Reliable routing while troubleshooting numeric artifact typing |

Both use the same check job and publish `disk_use_percent` plus `disk_tier`.

**After import, update environment-specific values:**

1. `job_template_id` on each AAP job step (if your Controller IDs differ from nostromo)
2. `credential_id` on each step
3. `test_disk_use_percent` on the check step — exported default is `50` (routes to Continue); change or remove for live disk checks

### 6. Configure the Switch Step

| Switch port | Condition | Remediate | Notify title |
|-------------|-----------|-----------|--------------|
| `<80%` | `disk_use_percent < 80` | Continue — no action | Disk Utilization OK (green) |
| `80-95%` | `>= 80 and <= 95` | Cleanup dnf cache + old logs | Warning — Disk Cleanup (orange) |
| `>95%` | `disk_use_percent > 95` | Expand EBS + grow filesystem | Critical — Disk Expanded (purple) |
| `default` | missing or non-numeric artifact | Fallback — manual review | Unsupported Disk Tier (red) |

After a check run, confirm **Input → Schema** on the Switch step shows `disk_use_percent` as `number`, not `string`.

### 7. Test Branches Without Filling the Disk

`check_disk.yml` accepts `test_disk_use_percent` as an extra var. When set, it skips live `df` and simulates usage for routing.

On the **Check** step in AO, set `extra_vars`:

| Branch | `test_disk_use_percent` |
|--------|-------------------------|
| Continue (`<80%`) | `75` |
| Cleanup (`80-95%`) | `85` |
| Expand (`>95%`) | `96` |
| Default / fallback | omit `test_disk_use_percent` on a host with a missing mount, or pass a non-numeric value |

Remove `test_disk_use_percent` (or leave empty) for a real disk check.

## Verification

```bash
# Check live disk tier on the demo VM
ssh -i "$DISK_DEMO_SSH_KEY" ec2-user@"$DISK_DEMO_VM_IP" \
  'bash -s' < disk-utilization/test/show_disk_tier.sh

# Launch workflow from AO UI with test_disk_use_percent=75
# Expected: Continue → green Mattermost notification

# Launch with test_disk_use_percent=85
# Expected: Cleanup → orange Mattermost notification with reclaimed space stats

# Launch with test_disk_use_percent=96
# Expected: Expand → purple Mattermost notification with before/after volume size
```

## Live Disk Testing (Optional)

```bash
ssh -i "$DISK_DEMO_SSH_KEY" ec2-user@"$DISK_DEMO_VM_IP"

./show_disk_tier.sh        # see current tier
./fill_disk.sh 85          # trigger warn
./fill_disk.sh 96          # trigger critical
```

Copy `disk-utilization/test/*.sh` to the VM first, or run from the repo checkout on the host.

## Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| AAP Gateway | 443 / 8444 | AAP UI and API |
| AO UI | 8080 | automation orchestrator web interface |
| Mattermost | 8065 | Chat notifications |
| SSH | 22 | Ansible connection to demo VM |
