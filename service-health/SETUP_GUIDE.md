# Service Health Demo - Full Setup Guide

## Infrastructure Required

| Component | Purpose | How to Provision |
|-----------|---------|------------------|
| AAP 2.7 with AO | Controller + automation orchestrator | `aws-aap-containerized` repo or existing AAP install |
| Demo VM | RHEL 9 EC2 target host running (or missing) the `httpd` service | EC2 t3.small in `us-east-1` (or your region) |
| Package repos | `dnf` access on the target so the install path can add `httpd` | RHEL subscription or a local mirror reachable from the VM |
| Mattermost | Per-state service health notifications | Container on bastion (or reuse an existing Mattermost instance) |

## Step-by-Step Setup

### 1. Provision Demo VM

```bash
cd ~/work/src/aap-orchestrator-demos

# Create EC2 key pair
aws ec2 create-key-pair --key-name ao-svc-demo-key \
  --query 'KeyMaterial' --output text --region us-east-1 > ao-svc-demo-key.pem
chmod 600 ao-svc-demo-key.pem

# Launch RHEL 9 instance (adjust AMI for your region)
aws ec2 run-instances \
  --image-id ami-0d85f16af633ab171 \
  --instance-type t3.small \
  --key-name ao-svc-demo-key \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ao-svc-demo-vm}]' \
  --region us-east-1

# Export connection details for inventory
export SVC_DEMO_VM_IP=<VM_PUBLIC_IP>
export SVC_DEMO_SSH_KEY=$PWD/ao-svc-demo-key.pem

# Verify SSH and install the demo service for the "active" path
ssh -i "$SVC_DEMO_SSH_KEY" ec2-user@"$SVC_DEMO_VM_IP" \
  'sudo dnf install -y httpd && sudo systemctl enable --now httpd && systemctl is-active httpd'
```

The `become: true` playbooks manage `httpd` (or any systemd unit passed as `service_name`) with `service_facts`, `systemd`, and `dnf`. The target must be RHEL family so the install path's `dnf` task runs.

### 2. Configure AAP Project and Inventory

1. **Project** — sync this repo (or `service-health/` subtree) from Git.
2. **Inventory** — create a host that matches the trigger's default `host` value (`node1`), or edit the trigger to match your inventory:

| Host | `ansible_host` | Notes |
|------|----------------|-------|
| `node1` | VM public IP | `ec2-user`, SSH key credential |

The workflow trigger passes the target through `limit: "${trigger.host}"`, so the inventory hostname must equal the `host` input you launch with.

### 3. Register Job Templates

Create six job templates from `service-health/playbooks/`. The **Name** column must match the `job_template_name` values in `ao/service-health-101.json` exactly.

| Name | Playbook | Runs on |
|------|----------|---------|
| Service Health - Check Service | `check_service.yml` | target host |
| Service Health - Log OK | `remediate_log_ok.yml` | target host |
| Service Health - Start Service | `remediate_start_service.yml` | target host |
| Service Health - Restart Service | `remediate_restart_service.yml` | target host |
| Service Health - Install Service | `remediate_install_service.yml` | target host |
| Service Health - Notify Chatroom | `notify_chatroom.yml` | localhost |

**Credentials:**

- SSH Machine credential on the five host-facing templates (Check, Log OK, Start, Restart, Install).
- No SSH needed on Notify — `notify_chatroom.yml` runs `hosts: localhost` / `connection: local`.

Enable **Prompt on launch → Extra Variables** and **Limit** on these templates so AO can pass `service_name`, `service_state`, the notify artifacts, and the `${trigger.host}` limit at run time.

### 4. Configure Notifications (Mattermost)

`notify_chatroom.yml` posts a colored Mattermost attachment per service state using `community.general.mattermost`. It requires:

| Variable | Purpose |
|----------|---------|
| `api_chat_token` | Mattermost bot API token (required) |
| `mattermost_server` | Host:port (default `44.209.231.244:8065`) |

The message color is chosen from `service_state`: `active` green (`#4ade80`), `inactive` amber (`#fbbf24`), `failed` orange (`#f97316`), `not-found` red (`#ef4444`).

```bash
# Login (adjust host and credentials)
MM_TOKEN=$(curl -s http://<bastion>:8065/api/v4/users/login \
  -H "Content-Type: application/json" \
  -d '{"login_id":"admin","password":"changeme123"}' -D - | grep "^token:" | awk '{print $2}')

# Create a bot account and token, then store it as api_chat_token on the
# "Service Health - Notify Chatroom" job template (or pass it from AO).
```

### 5. Import AO Workflow

Import the workflow JSON into automation orchestrator:

| File | Trigger inputs | Switch routes on |
|------|----------------|------------------|
| [`ao/service-health-101.json`](ao/service-health-101.json) | `host` (default `node1`), `service_name` (default `httpd`) | `service_state` (`active` / `inactive` / `failed` / `not-found`) |

The `Check Service` node publishes `service_state`, `service_name`, and `notify_host` via `set_stats`; the switch reads `${check_service.artifacts.service_state}` and each remediation node fans out to a `Service Health - Notify Chatroom` job.

**After import, update environment-specific values:**

1. `credential_id` on every node — the exported value is the placeholder `YOUR_AAP_CREDENTIAL_ID`. Replace with your Controller's credential ID.
2. `job_template_name` / `organization_name` — confirm they match the templates and organization you created (`organization_name` is exported as `Default`).
3. Adjust the trigger's `host` default if your inventory hostname is not `node1`.

### 6. Configure the Switch Node

The switch (`Switch on service_state`) has four labeled conditions. Each maps to one remediation job template, which then fans out to a notify job.

| Switch label | Condition | Remediation JT | Notify node | Color |
|--------------|-----------|----------------|-------------|-------|
| `active` (`case_0`) | `${check_service.artifacts.service_state} == 'active'` | Service Health - Log OK | Notify — Active | green |
| `inactive` (`case_1`) | `${check_service.artifacts.service_state} == 'inactive'` | Service Health - Start Service | Notify — Started | amber |
| `failed` (`case_2`) | `${check_service.artifacts.service_state} == 'failed'` | Service Health - Restart Service | Notify — Restarted | orange |
| `not-found` (`case_3`) | `${check_service.artifacts.service_state} == 'not-found'` | Service Health - Install Service | Notify — Installed | red |

Each remediation node receives `service_name` and `service_state` from the check node's artifacts and publishes `remediation_action`, `service_state_before`, and `service_state_after` for the downstream notify node.

## Test / Verification

Launch the workflow from the AO UI with the trigger inputs `host` and `service_name` (default `httpd`). Drive each branch by changing the service state on the target VM first.

```bash
# active path — service running (initial state after step 1)
ssh -i "$SVC_DEMO_SSH_KEY" ec2-user@"$SVC_DEMO_VM_IP" 'sudo systemctl start httpd'
# Launch workflow (host=node1, service_name=httpd)
# Expected: service_state=active → Log OK → green "Log OK" notification

# inactive path — service stopped
ssh -i "$SVC_DEMO_SSH_KEY" ec2-user@"$SVC_DEMO_VM_IP" 'sudo systemctl stop httpd'
# Expected: service_state=inactive → Start Service → amber "Start Service" notification

# failed path — force a failed unit
ssh -i "$SVC_DEMO_SSH_KEY" ec2-user@"$SVC_DEMO_VM_IP" \
  'echo "ExecStartPre=/bin/false" | sudo tee /etc/systemd/system/httpd.service.d/fail.conf; \
   sudo systemctl daemon-reload; sudo systemctl restart httpd; systemctl is-failed httpd'
# Expected: service_state=failed → Restart Service (resets failed state, restarts) → orange notification
# Clean up: remove the drop-in and daemon-reload before other tests

# not-found path — remove the package
ssh -i "$SVC_DEMO_SSH_KEY" ec2-user@"$SVC_DEMO_VM_IP" 'sudo dnf remove -y httpd'
# Expected: service_state=not-found → Install Service (dnf install + enable) → red notification
```

`check_service.yml` derives `service_state` from `service_facts`: missing unit → `not-found`, `running` → `active`, `failed` → `failed`, otherwise → `inactive`. To test a different unit (e.g. `nginx`, `postgresql`), set `service_name` on the trigger.

## Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| AAP Gateway | 443 / 8444 | AAP UI and API |
| AO UI | 8080 | automation orchestrator web interface |
| Mattermost | 8065 | Chat notifications |
| SSH | 22 | Ansible connection to demo VM |
