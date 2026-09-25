# User Lifecycle Demo - Full Setup Guide

This demo routes user lifecycle requests by `request_type` — `new_hire`, `contractor`,
`role_change`, or `termination` — using an automation orchestrator (AO) switch node.
A `Process Request` job validates the input and republishes `request_type` as an
artifact; the switch then fans out to the matching provisioning/termination job, and
every branch ends with a Mattermost notification.

## Infrastructure Required

| Component | Purpose | How to Provision |
|-----------|---------|------------------|
| AAP 2.7 with AO | Controller + automation orchestrator | `aws-aap-containerized` repo or existing AAP install |
| Demo VM | RHEL 9 target host where accounts are created, modified, and terminated | EC2 t3.small in `us-east-1` (or your region) |
| Mattermost | Per-request-type notifications (IT / HR) | Container on bastion (or reuse an existing Mattermost instance) |

## Step-by-Step Setup

### 1. Provision Demo VM

```bash
cd ~/work/src/aap-orchestrator-demos

# Create EC2 key pair
aws ec2 create-key-pair --key-name ao-user-demo-key \
  --query 'KeyMaterial' --output text --region us-east-1 > ao-user-demo-key.pem
chmod 600 ao-user-demo-key.pem

# Launch RHEL 9 instance (adjust AMI for your region)
aws ec2 run-instances \
  --image-id ami-0d85f16af633ab171 \
  --instance-type t3.small \
  --key-name ao-user-demo-key \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ao-user-demo-vm}]' \
  --region us-east-1

# Export connection details for inventory
export USER_DEMO_VM_IP=<VM_PUBLIC_IP>
export USER_DEMO_SSH_KEY=$PWD/ao-user-demo-key.pem

# Verify SSH
ssh -i "$USER_DEMO_SSH_KEY" ec2-user@"$USER_DEMO_VM_IP" 'id'
```

The provisioning, role-change, and termination playbooks use `become: true`, so the SSH
Machine credential must have privilege escalation (sudo) enabled.

### 2. Configure AAP Project and Inventory

1. **Project** — sync this repo (or the `user-lifecycle/` subtree) from Git.
2. **Inventory** — create a host for the demo VM:

| Host | `ansible_host` | Notes |
|------|----------------|-------|
| `user-demo-vm` | VM public IP | `ec2-user`, SSH key credential with sudo |

The account-management playbooks target `hosts: "{{ _host | default('all') }}"`, so the
inventory the job template runs against determines where accounts are created or removed.
Point the job templates at an inventory that contains only `user-demo-vm` for the demo.

### 3. Register Job Templates

Create six job templates from `user-lifecycle/playbooks/`. The **Name** column must match
the `job_template_name` values in the AO workflow JSON exactly.

| Name | Playbook | Runs on |
|------|----------|---------|
| User Lifecycle - Process Request | `process_request.yml` | localhost |
| User Lifecycle - Provision New Hire | `provision_new_hire.yml` | `user-demo-vm` |
| User Lifecycle - Provision Contractor | `provision_contractor.yml` | `user-demo-vm` |
| User Lifecycle - Update Role | `update_role.yml` | `user-demo-vm` |
| User Lifecycle - Terminate User | `terminate_user.yml` | `user-demo-vm` |
| Notify Chatroom | `notify_chatroom.yml` | localhost |

**Credentials:**

- SSH Machine credential (with sudo) on the four account-management templates
  (Provision New Hire, Provision Contractor, Update Role, Terminate User).
- No SSH needed on `User Lifecycle - Process Request` or `Notify Chatroom` — both run on
  localhost with `connection: local`.

**Prompt on launch → Extra Variables:** enable this on every template so AO can pass the
switch inputs (`request_type`, `target_username`, `user_groups`, `contract_days`) and the
notify artifacts described below.

### 4. Configure Notify (Mattermost)

`notify_chatroom.yml` posts a colored Mattermost attachment whose title and color are
derived from `request_type` (green = new_hire, blue = contractor, yellow = role_change,
red = termination). It requires two variables:

| Variable | Purpose |
|----------|---------|
| `api_chat_token` | Mattermost bot API token (required — no default) |
| `mattermost_server` | Host:port (default `44.209.231.244:8065`) |

```bash
# Login (adjust host and credentials)
MM_TOKEN=$(curl -s http://<bastion>:8065/api/v4/users/login \
  -H "Content-Type: application/json" \
  -d '{"login_id":"admin","password":"changeme123"}' -D - | grep "^token:" | awk '{print $2}')

# Create a bot account + token, or use an incoming webhook.
# Store the bot token as api_chat_token on the Notify Chatroom job template
# (or pass it from AO), and set mattermost_server to your instance.
```

The workflow calls `Notify Chatroom` once per branch, mapping the upstream job's
artifacts into the notification. New-hire/contractor/termination pass `action_taken`,
`target_username`, and `notify_host`; contractor also passes `account_expiry`; role_change
also passes `groups_before` and `groups_after`.

### 5. Triggering Options

The demo ships with a **manual trigger** whose `input_schema` accepts:

| Field | Required | Default | Purpose |
|-------|----------|---------|---------|
| `request_type` | yes | `new_hire` | `new_hire`, `contractor`, `role_change`, or `termination` |
| `target_username` | yes | (empty) | Username to provision, modify, or terminate |
| `requestor` | no | `admin` | Person or system requesting the action |
| `user_groups` | no | `users` | Comma-separated groups for the user |
| `contract_days` | no | `90` | Days until contractor account expiry |

**Survey option** — expose these same fields as an AO survey (or a Controller survey on
`User Lifecycle - Process Request`) so a human maps `request_type` from a dropdown of the
four values. This is the interactive demo path.

**Webhook option** — replace/supplement the manual trigger with a webhook that posts the
same JSON payload (`request_type`, `target_username`, `requestor`, `user_groups`,
`contract_days`). A ticketing/HR system can then drive the workflow unattended. Either
way, `Process Request` validates the input and fails fast on a missing or invalid
`request_type` or `target_username`.

## Import AO Workflow

Import the workflow JSON into automation orchestrator:

| File | Switch routes on | Trigger |
|------|------------------|---------|
| [`ao/user-lifecycle-101.json`](ao/user-lifecycle-101.json) | `request_type` (`new_hire` / `contractor` / `role_change` / `termination`) | Manual trigger / survey / webhook |

**After import, update environment-specific values:**

1. `job_template` (the `job_template_name` on each AAP job node) if you named your
   templates differently — they must resolve to real templates in your Controller.
2. `credential_id` / `credential` on each node for your Controller's credentials.
3. `organization_name` — the JSON uses `Default`; change if your templates live in
   another organization.

## Configure the Switch Node

The `Route by request_type` switch reads the artifact republished by `Process Request`
(`${process_request.artifacts.request_type}`) and routes to one job per value.

| Switch label | Condition | Job Template | Runbook playbook |
|--------------|-----------|--------------|------------------|
| `new_hire` | `request_type == 'new_hire'` | User Lifecycle - Provision New Hire | `provision_new_hire.yml` |
| `contractor` | `request_type == 'contractor'` | User Lifecycle - Provision Contractor | `provision_contractor.yml` |
| `role_change` | `request_type == 'role_change'` | User Lifecycle - Update Role | `update_role.yml` |
| `termination` | `request_type == 'termination'` | User Lifecycle - Terminate User | `terminate_user.yml` |

Each branch then flows to `Notify Chatroom`. `Process Request` lowercases and trims
`request_type` before publishing, so the switch always compares against clean values.

## Test / Verification

Exercise each branch by launching the workflow (or posting the webhook payload) with the
matching `request_type`. Use a throwaway `target_username` on the demo VM.

```bash
# new_hire → Provision New Hire → green Mattermost notification
#   request_type=new_hire  target_username=alice  user_groups=users,developers

# contractor → Provision Contractor → blue notification with account_expiry
#   request_type=contractor  target_username=bob  user_groups=users,contractors  contract_days=30

# role_change → Update Role → yellow notification with groups_before/groups_after
#   request_type=role_change  target_username=alice  user_groups=users,admins

# termination → Terminate User → red notification
#   request_type=termination  target_username=alice
```

Confirm results on the demo VM after each run:

```bash
ssh -i "$USER_DEMO_SSH_KEY" ec2-user@"$USER_DEMO_VM_IP"

id alice                              # new_hire: user + groups exist
sudo chage -l bob                     # contractor: account expiry set
id -Gn alice                          # role_change: updated group membership
sudo passwd -S alice                  # termination: account locked (L)
ls /var/archive/terminated/           # termination: archived home tarball
```

Invalid input is a valid test too: launch with an empty `target_username` or a bogus
`request_type` (for example `intern`) and confirm `Process Request` fails with the
validation message before the switch runs.

## Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| AAP Gateway | 443 / 8444 | AAP UI and API |
| AO UI | 8080 | automation orchestrator web interface |
| Mattermost | 8065 | Chat notifications |
| SSH | 22 | Ansible connection to demo VM |
