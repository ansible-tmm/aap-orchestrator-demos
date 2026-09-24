# Cert Demo 101 - Full Setup Guide

## Infrastructure Required

| Component | Purpose | How to Provision |
|-----------|---------|-----------------|
| AAP 2.7 with AO | Controller + automation orchestrator | `aws-aap-containerized` repo or `aap-images` |
| SSL for AAP | AO needs HTTPS to AAP | `ansible_platform_ssl` repo with `mcp_proxy_enabled: true` |
| Demo VM | nginx + api-server with certs | EC2 t3.small, provisioned by setup playbooks |
| Splunk | Cert monitoring + alerts | Container on bastion (or OCP) |
| Mattermost | Notifications | Container on bastion (or OCP) |
| LiteLLM | AI proxy for AO agent steps | Container on bastion |

## Step-by-Step Setup

### 1. Provision AAP with MCP and SSL

```bash
# Set env vars
export INSTANCE_NAME=ao-cert-demo
export INSTALLER_ADMIN_PW='ansible123!'
export AAP_INCLUDE_MCP_SERVER=true
export AAP_INCLUDE_EDA_CONTROLLER=true
export AAP_INCLUDE_AUTOMATION_HUB=true

# Provision EC2 + install AAP
cd ~/work/src/aws-aap-containerized
ansible-playbook playbooks/aws/create_infrastructure.yml
ansible-playbook playbooks/aap/install.yml

# Add SSL (needs DNS record pointing to the AAP IP)
cd ~/work/src/ansible_platform_ssl
ansible-playbook update_cert_containerized.yml \
  -e dns_name="aoaap.demoredhat.com" \
  -e mcp_proxy_enabled=true
```

### 2. Provision Demo VM

```bash
cd ~/work/src/aap-orchestrator-demos

# Create EC2 key pair
aws ec2 create-key-pair --key-name ao-cert-demo-key \
  --query 'KeyMaterial' --output text --region us-east-1 > ao-cert-demo-key.pem
chmod 600 ao-cert-demo-key.pem

# Launch VM
aws ec2 run-instances \
  --image-id ami-0d85f16af633ab171 \
  --instance-type t3.small \
  --key-name ao-cert-demo-key \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ao-cert-demo-vm}]' \
  --region us-east-1

# Create DNS record (Route 53)
# Point certdemo.demoredhat.com to the VM's public IP

# Provision nginx + Vault
ansible-playbook -i cert-lifecycle/inventory/hosts.yml \
  cert-lifecycle/setup/provision_vm.yml \
  -e ansible_ssh_private_key_file=$PWD/ao-cert-demo-key.pem \
  -e ansible_host=<VM_IP>

# Provision api-server (Tomcat/Java keystore)
ansible-playbook -i cert-lifecycle/inventory/hosts.yml \
  cert-lifecycle/setup/provision_tomcat.yml \
  -e ansible_ssh_private_key_file=$PWD/ao-cert-demo-key.pem \
  -e ansible_host=<VM_IP>

# Generate expired certs for demo
ansible-playbook -i cert-lifecycle/inventory/hosts.yml \
  cert-lifecycle/setup/generate_expired_cert.yml \
  -e ansible_ssh_private_key_file=$PWD/ao-cert-demo-key.pem \
  -e ansible_host=<VM_IP>
```

### 3. Trust the Vault CA on your Mac

```bash
# Download CA cert from Vault
ssh -i ao-cert-demo-key.pem ec2-user@<VM_IP> \
  "curl -s http://127.0.0.1:8200/v1/ansible/data/certificate -H 'X-Vault-Token: demo-root-token'" \
  | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['data']['data']['ca_cert']).decode())" \
  > /tmp/vault-ca.pem

# Trust it (macOS)
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain /tmp/vault-ca.pem
```

### 4. Provision Lab Services (Splunk, Mattermost, LiteLLM)

```bash
# On bastion or any host that can reach the demo VM
ansible-playbook cert-lifecycle/setup/provision_lab_services.yml \
  -e SPLUNK_PASSWORD='yourpassword' \
  -e ANTHROPIC_API_KEY='sk-ant-...' \
  -e CERT_DEMO_HOST='certdemo.demoredhat.com'
```

Or manually:

```bash
# Splunk
sudo podman run -d --name splunk --restart always \
  -p 8000:8000 -p 8088:8088 -p 8089:8089 \
  -e SPLUNK_START_ARGS="--accept-license" \
  -e SPLUNK_PASSWORD="changeme123" \
  docker.io/splunk/splunk:latest

# Mattermost
sudo podman run -d --name mattermost --restart always \
  -p 8065:8065 \
  docker.io/mattermost/mattermost-preview:latest

# LiteLLM (create config first)
cat > /tmp/litellm_config.yaml << EOF
model_list:
  - model_name: claude-sonnet-4-6
    litellm_params:
      model: anthropic/claude-sonnet-4-6-20250514
      api_key: sk-ant-YOUR_KEY_HERE

general_settings:
  master_key: sk-demo-key
EOF

sudo podman run -d --name litellm --restart always \
  -p 4000:4000 \
  -v /tmp/litellm_config.yaml:/app/config.yaml:ro \
  ghcr.io/berriai/litellm:main-latest \
  --config /app/config.yaml --port 4000
```

### 5. Setup Cert Monitoring Scripts

On the bastion/monitoring host:

```bash
# Create cert check script (monitors both nginx:443 and api-server:8443)
cat > /tmp/check_cert.sh << 'SCRIPT'
#!/bin/bash
for ENTRY in "certdemo.demoredhat.com:443:nginx:pem" "certdemo.demoredhat.com:8443:api-server:java_keystore"; do
  HOST=$(echo $ENTRY | cut -d: -f1)
  PORT=$(echo $ENTRY | cut -d: -f2)
  SVC=$(echo $ENTRY | cut -d: -f3)
  CTYPE=$(echo $ENTRY | cut -d: -f4)
  ENDDATE=$(echo | openssl s_client -connect ${HOST}:${PORT} -servername ${HOST} 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
  if [ -z "$ENDDATE" ]; then
    echo "{\"host\": \"${HOST}\", \"orig_host\": \"${HOST}\", \"cert_cn\": \"${HOST}\", \"service\": \"${SVC}\", \"port\": ${PORT}, \"cert_type\": \"${CTYPE}\", \"status\": \"unreachable\", \"days_remaining\": -999}"
    continue
  fi
  EXPIRY_EPOCH=$(date -d "${ENDDATE}" +%s 2>/dev/null)
  NOW_EPOCH=$(date +%s)
  DAYS_REMAINING=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
  if [ ${DAYS_REMAINING} -le 0 ]; then STATUS="expired"
  elif [ ${DAYS_REMAINING} -le 7 ]; then STATUS="critical"
  elif [ ${DAYS_REMAINING} -le 30 ]; then STATUS="warning"
  else STATUS="valid"; fi
  echo "{\"host\": \"${HOST}\", \"orig_host\": \"${HOST}\", \"cert_cn\": \"${HOST}\", \"service\": \"${SVC}\", \"port\": ${PORT}, \"cert_type\": \"${CTYPE}\", \"status\": \"${STATUS}\", \"days_remaining\": ${DAYS_REMAINING}, \"expiry_date\": \"${ENDDATE}\", \"issuer\": \"Demo Certificate Authority\"}"
done
SCRIPT
chmod +x /tmp/check_cert.sh

# Create push script
cat > /tmp/push_cert_to_splunk.sh << 'EOF'
#!/bin/bash
/tmp/check_cert.sh | while read RESULT; do
  curl -sk https://localhost:8088/services/collector/event \
    -H "Authorization: Splunk <HEC_TOKEN>" \
    -d "{\"event\": ${RESULT}, \"sourcetype\": \"cert_monitor\", \"index\": \"main\"}" > /dev/null 2>&1
done
EOF
chmod +x /tmp/push_cert_to_splunk.sh

# Add cron (every minute)
(crontab -l 2>/dev/null; echo "* * * * * /tmp/push_cert_to_splunk.sh") | crontab -
```

### 6. Configure Splunk Alert

In Splunk UI:
1. Search: `index=main sourcetype=cert_monitor days_remaining<7 earliest=-5m | head 1`
2. Save As > Alert
3. Title: `Certificate Expiry Alert`
4. Scheduled, cron: `*/4 * * * *`
5. Trigger: Once, throttle 300 seconds
6. Add Action > Webhook: `http://<AO_HOST>:8080/api/v1/webhooks/splunk-cert-alert`

### 7. Register AAP Job Templates

```bash
AAP="https://aoaap.demoredhat.com:8444"
AUTH="admin:ansible123!"

# Create project
curl -sk "${AAP}/api/controller/v2/projects/" -u "${AUTH}" \
  -H "Content-Type: application/json" \
  -d '{"name":"Cert Rotation Demo","organization":1,"scm_type":"git","scm_url":"https://github.com/anshulbehl/aap-orchestrator-demos.git","scm_branch":"main","scm_update_on_launch":true}'

# Create inventory + host + group
# Create Machine credential with SSH key
# Create job templates: Renew Certificate, Renew Java Keystore Certificate, Validate Cert Renewal, Notify Mattermost
# Associate credentials with templates
# Add host variables including cert_domain, vault config, cert_services mapping
```

See the AAP API commands used during this session for the exact curl commands.

### 8. Configure AO

1. Create AI credential (LiteLLM): base_url=`http://<bastion>:4000/v1`, api_key=`sk-demo-key`, model=`claude-sonnet-4-6`
2. Create AAP credential: host=`https://aoaap.demoredhat.com:8444`, token
3. Import workflow JSON: `cert-demo-101.json` (manual trigger) and `cert-demo-101-webhook.json` (Splunk webhook)

### 9. Create Mattermost Webhook

```bash
# Login
MM_TOKEN=$(curl -s http://<bastion>:8065/api/v4/users/login \
  -H "Content-Type: application/json" \
  -d '{"login_id":"admin","password":"changeme123"}' -D - | grep "^token:" | awk '{print $2}')

# Get team ID
TEAM_ID=$(curl -s http://<bastion>:8065/api/v4/teams \
  -H "Authorization: Bearer ${MM_TOKEN}" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")

# Get channel ID
CHANNEL_ID=$(curl -s "http://<bastion>:8065/api/v4/teams/${TEAM_ID}/channels" \
  -H "Authorization: Bearer ${MM_TOKEN}" | python3 -c "import sys,json; [print(c['id']) for c in json.load(sys.stdin) if c['name']=='town-square']")

# Create webhook
curl -s http://<bastion>:8065/api/v4/hooks/incoming \
  -H "Authorization: Bearer ${MM_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"channel_id\":\"${CHANNEL_ID}\",\"display_name\":\"Cert Lifecycle Bot\"}"
```

### 10. Demo Reset (Expire Certs)

```bash
cd ~/work/src/aap-orchestrator-demos

# Expire nginx cert
ansible-playbook -i cert-lifecycle/inventory/hosts.yml \
  cert-lifecycle/setup/generate_expired_cert.yml \
  -e ansible_ssh_private_key_file=$PWD/ao-cert-demo-key.pem \
  -e ansible_host=<VM_IP>

# Expire api-server cert
ansible-playbook -i cert-lifecycle/inventory/hosts.yml \
  cert-lifecycle/setup/provision_tomcat.yml \
  -e ansible_ssh_private_key_file=$PWD/ao-cert-demo-key.pem \
  -e ansible_host=<VM_IP> \
  --start-at-task="Pull CA certificate from Vault"
```

## Verification

```bash
# Check nginx cert (should show expired)
echo | openssl s_client -connect certdemo.demoredhat.com:443 2>/dev/null | openssl x509 -noout -dates

# Check api-server cert (should show expired)
echo | openssl s_client -connect certdemo.demoredhat.com:8443 2>/dev/null | openssl x509 -noout -dates

# After AO workflow runs and renews:
# Both should show valid dates ~90 days out
```

## Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| AAP Gateway | 443 (proxied to 8444 via nginx SSL) | AAP UI and API |
| AAP MCP | 8448 (proxied to 8449 via nginx SSL) | MCP server |
| AO API | 8000 | automation orchestrator API |
| AO UI | 8080 | automation orchestrator web interface |
| AO Webhooks | 8080 | Webhook triggers |
| Splunk UI | 8000 | Splunk web interface |
| Splunk HEC | 8088 | HTTP Event Collector |
| Splunk Mgmt | 8089 | Management API |
| Mattermost | 8065 | Chat |
| LiteLLM | 4000 | AI proxy |
| Demo nginx | 443 | PEM cert service |
| Demo api-server | 8443 | Java keystore cert service |
| Vault | 8200 | HashiCorp Vault (on demo VM) |
