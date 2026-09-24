# Intelligent Certificate Renewal with automation orchestrator
## Live Demo Script

**Audience:** Tech preview customers, technical evaluators, Solutions Architects  
**Format:** Live demo with narration (~8 minutes)  
**Last updated:** 2026-06-29

---

> **Important framing guidance**
>
> This demo is an **example of what you can build with Automation orchestrator** — not a prescriptive solution customers should deploy as-is. Certificate management is the use case chosen to illustrate AO's core capabilities: event-driven triggers, Task agents, human-in-the-loop approvals, and dynamic AAP job execution.
>
> Every customer's workflow will look different based on their certificate authority, monitoring stack, approval process, and infrastructure. The patterns are transferable. The specific workflow is a starting point.
>
> When presenting, make this clear early: *"We're using certificate management as the example, but the same building blocks apply to patch management, compliance enforcement, incident remediation, or any automated process you want to make more intelligent."*

---

## Demo Flow Overview

| Section | What You Show | Time |
|---|---|---|
| Opening | Context and problem statement | ~1 min |
| Two Services | Both sites healthy, side by side | ~1 min |
| Simulating the Incident | Expire both certs live from AAP | ~1 min |
| Splunk Detection | Both events indexed, alert fires | ~1 min |
| AO Receives Alerts | Two simultaneous workflow runs | ~30 sec |
| AI Agent Plans | Two different decisions, same workflow | ~2 min |
| Approval + Execution | Human in the loop, AAP runs | ~1 min |
| Services Restored | Both sites healthy again | ~30 sec |
| Closing | Key takeaways | ~30 sec |

---

## Pre-Demo Checklist

- [ ] Both browser windows open: `certdemo.demoredhat.com` (port 443) and `certdemo.demoredhat.com:8443`
- [ ] AAP UI logged in, Templates page visible
- [ ] AO Workflow Runs page open in a separate tab
- [ ] Splunk search tab ready:
  ```
  index=main sourcetype=cert_monitor earliest=-5m | dedup service sortby -_time | where days_remaining<7
  ```
- [ ] Both certificates must be **valid** at the start — expire them live during the demo
- [ ] Confirm Splunk alert is enabled with webhook pointing to AO

---

## Script

### Opening (~1 min)

Hi, I'm [Your Name], Technical Marketing Manager from the Ansible team at Red Hat. Today I'm going to show you Ansible Automation orchestrator in action — using certificate lifecycle management as our example use case.

Before I start: what I'm showing you is one workflow we built to illustrate what AO makes possible. The use case is certificate management, but the patterns — event-driven triggers, an AI agent that reasons and plans, human approval gates, dynamic AAP job execution — these apply to any automation challenge you're working on. Patch management, compliance enforcement, incident remediation. The building blocks are the same.

We chose certificate management because it's a problem every organization has, the stakes are clear — 77% of organizations have experienced outages from expired certificates costing up to $72,000 per hour — and it has an interesting technical challenge: different certificate types require completely different renewal automation. A PEM file on nginx and a Java Keystore on an API server need different playbooks, different restart procedures, and different risk handling.

That challenge is a perfect way to show what makes AO different. Let me show you.

---

### Two Services, Two Certificate Types (~1 min)

> **Action:** Show both browser windows side by side — Parasol Insurance on port 443 and Internal Platform API on port 8443. Both should show valid, trusted certificates.

We have two services running on the same host.

On the left: the Parasol Insurance website — a customer-facing site secured by nginx using a PEM certificate on port 443. On the right: the Internal Platform API — an enterprise API gateway secured by a Java Keystore certificate on port 8443.

Two different services. Two different certificate types. Both healthy right now.

This is your normal production state. The goal of this demo is to show what happens when both go wrong at the same time — and how Automation orchestrator handles it without a human figuring out which playbook to run for which service.

---

### Simulating the Incident (~1 min)

> **Action:** Switch to AAP UI. Navigate to Templates. Launch "Expire Nginx Certificate" and "Expire API Server Certificate" back to back.

I'm going to simulate what happens when both certificates expire simultaneously — a scenario that happens during cert authority migrations, missed renewals, or bulk certificate operations.

> **Action:** Switch back to the two browser windows. Refresh both. Both show the certificate error page.

Two services down. Two different certificate types. Both blocking users. This is the incident.

Traditionally, someone gets paged, has to figure out which cert type each service uses, find the right runbook, and manually execute the correct renewal procedure for each. That's time, risk, and human error in every step.

We're going to let Automation orchestrator handle it — intelligently.

---

### Splunk Detects the Incident (~1 min)

> **Action:** Switch to Splunk. Run the search:
> ```
> index=main sourcetype=cert_monitor earliest=-5m | dedup service sortby -_time | where days_remaining<7
> ```

We have Splunk monitoring both services. A monitoring script runs every 10 seconds, checking the TLS status of both endpoints and pushing structured events to Splunk.

Within seconds of the certificates expiring, Splunk has indexed both events. You can see service nginx on port 443 — status expired, days remaining minus seven. And service api-server on port 8443 — also expired, also minus seven.

> **Action:** Point to the service and cert_type fields in the Splunk results.

The monitoring data includes the certificate type for each service. PEM for nginx. Java Keystore for the API server. This is the signal that Automation orchestrator will use to make intelligent decisions.

The Splunk alert fires automatically, sending both events as webhooks to Automation orchestrator. No human had to notice. No ticket had to be created first.

---

### Two Simultaneous Workflow Runs (~30 sec)

> **Action:** Switch to AO Workflow Runs page. Show two runs with status "Running" created at the same time.

Automation orchestrator has received two webhook alerts — one for each expired certificate. Two workflow runs started simultaneously. Same workflow definition. Different services.

This is the key point: one workflow handles both certificate types. The workflow itself doesn't know in advance which template to run. The AI agent figures that out at runtime.

---

### The AI Agent Plans the Remediation (~2 min)

> **Action:** Click into the first workflow run — the nginx one. Expand the Plan Renewal step to show the output JSON.

The Plan Renewal step is an AI agent running Claude Sonnet, connected to AAP via the Model Context Protocol. It received the Splunk payload and then used AAP's MCP tools to do its own analysis.

Here's what the agent did autonomously:
- Listed all available job templates in AAP and identified the ones relevant to certificate renewal
- Checked the inventory to confirm the target host exists — found cert-demo-vm with no active failures
- Read the host variables and found the cert_services mapping that maps each service to the correct renewal template
- Reviewed past job run history, confirming which execution patterns succeeded

> **Action:** Point to the output fields: selected_template, confidence, risk_level, recommendation.

The output: Selected template — **Renew Certificate**, the correct PEM renewal playbook for nginx. Confidence — 95%. Risk level — Low, just a service reload, no restart needed.

The agent didn't have this hardcoded. It reasoned its way to the answer.

> **Action:** Navigate to the second workflow run — the api-server one. Show the Plan Renewal output.

Now the same agent, same workflow, but for the api-server on port 8443.

Selected template: **Renew Java Keystore Certificate** — the correct template for a Java keystore renewal. Confidence: 97%. Risk level — the agent noted this requires a full service restart, not just a reload.

**Two services. Two AI decisions. No hardcoded routing. The agent understood the difference.**

> **Money moment:** Let the customer absorb this. Ask: *"What would your current process look like if both of these expired at 2am?"*

---

### Human in the Loop (~1 min)

> **Action:** Click "Review approval" on the first workflow run. Show the approval screen.

Now we're at the human-in-the-loop step. The operator sees the agent's full analysis — which template was selected, the confidence percentage, the risk level, the recommendation, and the reasoning behind it.

> **Action:** Point to the job_template_name field showing the dynamic expression.

Notice the job template expression: `${plan_renewal.result.content.selected_template}`

The template that will execute is whatever the agent decided. The operator isn't choosing which template to run — the agent already did that analysis. The operator is reviewing the reasoning and approving the action.

> **Action:** Click Approve. Switch to the second run and approve that as well.

Approved. AAP takes over. And approved for the api-server. AAP will now execute the Java Keystore renewal with the correct playbook.

---

### AAP Executes the Remediation (~30 sec)

> **Action:** Switch to AAP Jobs page. Show both renewal jobs — Renew Certificate and Renew Java Keystore Certificate — running or completed.

AAP is now executing both renewals. Renew Certificate for nginx — completed successfully. Renew Java Keystore Certificate for the api-server — completed successfully.

The same governance applies to both: RBAC controls who can run what, credentials are vault-managed and never exposed to the operator, and every action is in AAP's audit trail. Validate Cert Renewal runs automatically after each renewal, performing a TLS handshake to confirm the new certificate is healthy.

---

### Services Restored (~30 sec)

> **Action:** Show both browser windows side by side — both services loading cleanly with valid certificates.

Both services restored. Parasol Insurance website back online. Internal Platform API showing Certificate Valid, all endpoints responding.

Two different certificate types. Two different renewal strategies. One intelligent workflow. Zero manual intervention beyond the two approvals.

---

### Closing (~30 sec)

What you just saw is Ansible Automation orchestrator closing the loop between monitoring and remediation — intelligently.

Splunk detected the problem. The AI agent reasoned about the correct remediation strategy for each certificate type, using the actual AAP job template catalog, the actual inventory, and the actual job history. The operator reviewed and approved. AAP executed with full governance.

The workflow didn't have hardcoded if-statements for each certificate type. The agent figured it out at runtime. As you add new services, new certificate types, or new renewal strategies, the same workflow handles them — because the agent reasons, not routes.

And again — this is one example of what you can build with Automation orchestrator. Your certificate authority might be different. Your monitoring stack might be different. Your approval process might involve multiple teams. AO is flexible enough to handle all of that. What we've shown is the pattern: event-driven, AI-reasoned, human-governed, AAP-executed. That pattern works for any use case your team is trying to automate intelligently.

---

## Handling Common Questions

**"What if the agent picks the wrong template?"**  
The approval gate is exactly that safety net. The operator sees the agent's reasoning, the confidence score, and the recommended template before anything runs. A 95% confidence score means the agent checked real inventory data and real job history — not a guess. If something looks wrong, the operator rejects it.

**"How does the agent know about my specific certificate types?"**  
The agent uses AAP's MCP tools to read host variables live. In this demo, the host has a `cert_services` mapping. In a real environment, you'd configure this once per host. You can also rely on the agent reasoning from the service name and port alone.

**"Does this work without Splunk?"**  
Yes. The AO webhook trigger accepts alerts from any monitoring tool — Prometheus, Dynatrace, PagerDuty, or a manual curl. Splunk is the monitoring source in this demo. The workflow is monitoring-agnostic.

**"What's the difference between this and an EDA rulebook?"**  
EDA rulebooks are great for simple event-to-action mapping with known conditions. AO with an AI agent adds reasoning — the agent can discover available templates, assess risk, check history, and handle scenarios the workflow author didn't anticipate. EDA routes. The AI agent reasons.

**"Can I adapt this workflow for my use case?"**  
Yes — that's the point. The workflow JSON is in the `ao/` directory of this repo. The patterns (webhook trigger → AI agent → approval → AAP job → validate) apply to any automation scenario. Start from this template and adapt the prompt, job templates, and monitoring source to match your environment.

---

## Presenter Tips

- **Start with both sites healthy.** The contrast of before-and-after is the visual story. Don't skip the "everything is working" opening.
- **Let the two simultaneous runs sink in.** When the AO Workflow Runs page shows two parallel runs, pause. Ask: *"What would your current process look like if both of these expired at 2am?"*
- **The agent output comparison is the key moment.** Spend time on nginx (PEM, 95% confidence) vs api-server (Java Keystore, 97% confidence). The same workflow made two completely different, correct decisions.
- **Don't rush the approval screen.** Point to `${plan_renewal.result.content.selected_template}`. This is what makes it intelligent — the operator approves the agent's reasoning, not a static template name.
- **Reinforce the pattern, not the use case.** Certificate management is the example. Help the customer see how the same pattern applies to their problems.
- **Close with governance.** Every action is in AAP's audit trail. RBAC applies. Credentials are vault-managed. This is how organizations build confidence in AI-driven automation.
