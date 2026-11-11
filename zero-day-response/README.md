# Zero-Day Response: PHP2Shell

What do you do in the gap between the first exploitation attempt and the fix? This demo replays the PHP2Shell
zero-day (CVE-2026-109618, CVE-2026-109619) against a small RHEL estate on AWS and answers the four questions a board
asks, in order: **are we affected and were we already hit (KNOW), what have we done about it (CONTAIN), when is it
actually fixed (FIX), and can we prove it (PROVE)?**

AI reads. Owners decide. AAP acts. Automation orchestrator holds every lane until it is closed or explicitly owned.

- **KNOW:** evidence from every PHP asset and a log look-back run in parallel. A reviewed, deterministic
  classification ranks the assets (P1 to clear, plus "unknown" for an asset nobody can reach). AI explains the
  result for people; it cannot change it.
- **CONTAIN:** AI reads the recorded vendor advisories and extracts the interim controls, each cited to its
  document and section. A policy gate checks them against what the reviewed automation may do, a test host proves them, and two owners approve: security, and the payments service owner, who accepts an upload outage on the payments
  portal for a 72-hour exception window. Production is
  contained and verified, and AI drafts a board update that says what is verified and what is *not* claimed.
- **FIX:** the fix arrives unevenly. Automation orchestrator asks the Red Hat Security Data API per CVE, patches only
  where a fix exists (test, change approval, rolling patch with rollback), and removes the interim controls only
  where the fix is verified running.
- **PROVE:** a re-scan and an AI status draft that keeps the case open while one lane waits for a vendor (an appliance
  on end-of-life PHP 8.1) and one asset is still unknown.

This is a historical replay: the advisories are recorded snapshots (`advisories/`, checksums in `advisories/SHA256SUMS`), the vendor
timelines are real, the estate is a lab, and "AcmeCMS" is a simulated vendor. There is no exploit code: verification
uses benign requests and real business transactions.

## Workflows

| Workflow | File | Trigger | Approvals |
|---|---|---|---|
| Zero-Day Response - PHP2Shell: KNOW + CONTAIN | [`ao/flow-a-know-contain.json`](ao/flow-a-know-contain.json) | Manual, pre-filled (`SIR-PHP2SHELL-001`, `RHSB-2026-013`, both CVEs) | Incident commander (unknown asset), Security, Payments service; Engineer review only if the policy gate rejects the AI's spec |
| Zero-Day Response - PHP2Shell: FIX + PROVE | [`ao/flow-b-fix-prove.json`](ao/flow-b-fix-prove.json) | Manual, pre-filled (`SIR-PHP2SHELL-001`); schedule it for a real fix watch | Change |

Every AI step is followed by a `CHECK` step: the AI returns its answer as JSON text, and the `p2s-ai-output-check`
job template parses it and validates it against the schema in
[`playbooks/roles/p2s_response/files/ai_schemas.json`](playbooks/roles/p2s_response/files/ai_schemas.json) before
anything uses it. An empty or malformed answer fails visibly; it never flows on as empty data.

## Requirements

- A Red Hat Demo Platform **Ansible Product Demos** environment on AWS (AAP 2.7 with the LiteMaaS, AWS and APD
  Machine credentials preloaded), or an equivalent AAP 2.7 with those credentials.
- Automation orchestrator, installed by APD (below). Tested with automation orchestrator 1.3.1 and LiteMaaS
  `qwen3-235b`.
- AWS: six RHEL instances (three `t3.medium`, three `t3.small`; see `playbooks/node-config/nodes-aws.yml`) in
  `us-east-1`, about 10 minutes to build. Tear the estate down when you are done.

## Set up

1. In AAP, launch **APD | Single demo setup** and choose `infrastructure`.
2. Launch **Infrastructure | Automation Orchestrator | Install**. It installs automation orchestrator, wires the AAP
   and LiteMaaS integrations, and seeds both workflows and the demo's job templates (`p2s-*`). Its output ends
   with the automation orchestrator URL and the `admin` password.
3. Launch **p2s-estate-provision**. It creates a dedicated VPC (web ports reachable only inside it, SSH open) and the six tagged RHEL instances in `us-east-1`.
4. Update the **AWS Inventory** inventory source so the new instances and their tags appear.
5. Launch **p2s-estate-configure**. It builds every service at its baseline (vulnerable, except the
   already-patched marketing site): PHP versions, stacks, the vendor appliance and the look-back evidence.
6. Optional: launch **p2s-know-scan** to see the classification table before you start.

## Run

1. In automation orchestrator, open **Zero-Day Response - PHP2Shell: KNOW + CONTAIN** and run it (the trigger is
   pre-filled). Approve each owner step in its **Review approval** panel; the Security panel shows the AI's
   summary, the tested change and Red Hat's own residual-risk sentence.
2. Open **Zero-Day Response - PHP2Shell: FIX + PROVE** and run it. Approve the change.
3. To run again, launch **p2s-estate-configure** first: it resets the estate to the vulnerable baseline.

In this demo every approval step is assigned to `admin`. In production, give each step its own approver.

A typical run: KNOW + CONTAIN about 5 minutes plus your approval time, FIX + PROVE about 7 minutes.

## Tear down

Launch **p2s-estate-provision** with the extra variable `role_action: deprovision`, then update **AWS Inventory**.
Everything the demo created on AWS carries the tag `p2s-demo=true`.

## Job templates

| Job template | Playbook | What it does |
|---|---|---|
| `p2s-estate-provision` | `playbooks/infra_provision_aws.yml` | Creates (or, with `role_action: deprovision`, removes) the dedicated VPC and six tagged instances |
| `p2s-estate-configure` | `playbooks/estate_configure.yml` | Builds or resets the estate to its vulnerable baseline |
| `p2s-know-scan` | `playbooks/p2s_scan.yml` | KNOW: evidence from every PHP asset, then the deterministic classification |
| `p2s-know-lookback` | `playbooks/p2s_lookback.yml` | KNOW: were we already hit? (log look-back) |
| `p2s-ai-output-check` | `playbooks/p2s_ai_check.yml` | Parses and validates every AI answer against its schema |
| `p2s-contain-spec-check` | `playbooks/p2s_spec_check.yml` | Policy gate: is the AI-extracted control spec inside the reviewed envelope? |
| `p2s-contain-controls` | `playbooks/p2s_controls.yml` | CONTAIN: applies and verifies the interim controls (test, then production) |
| `p2s-fix-availability` | `playbooks/p2s_fix_availability.yml` | FIX: decides per stream on the Red Hat API answers the workflow recorded |
| `p2s-fix-patch` | `playbooks/p2s_patch.yml` | FIX: patch and verify (test, then rolling production with rollback) |
| `p2s-fix-standdown` | `playbooks/p2s_standdown.yml` | Removes interim controls only where the fix is verified |
| `p2s-prove-case-record` | `playbooks/p2s_case_record.yml` | PROVE: records the AI-drafted update on the case; refuses an empty draft |
| `p2s-independent-check` | `playbooks/p2s_independent_check.yml` | Independent read of live estate state and business transactions, outside the response roles |

## Using a different model

The prompts were written and tuned on one model and moved to another (LiteMaaS `qwen3-235b`). Treat a model change
like a code change:

- **Replay real inputs many times, before the new model touches anything.** One good run proves little. On the new
  model the advisory reader sometimes proposed a PHP 8.5-only setting (the test host caught it, because it checks
  the settings actually running); the human brief sometimes said a probe was "under triage"; the board update
  sometimes put one approval's time on another. Each was measured over dozens of calls and fixed in the prompt. The
  rates fell a long way, but not always to zero (2 of 180 replays still said "under forensic triage", and a few others had loose wording such as "exploit potential").
- **Treat replay rates as a floor.** Replays looked cleaner than live runs did, so judge a change on live runs too.
- **Test through the real platform, not just the model.** With a response schema, one provider path returned an
  empty answer that still looked like success. That is why every AI step here returns JSON as text and a
  deterministic `CHECK` step validates it.
- **Check meaning, not just shape.** A schema proves the fields exist. The policy gate, the test verification and
  the owner approvals decide; the AI's words only explain. `CHECK` validates shape only: nothing in the demo screens wording, and board
  updates are recorded without a sign-off step, so keep a human reading the words that reach people.
- **Don't ask for text nothing uses.** Asked for a reason on every service, the model invented some ("active exploit
  likely"). Prompt fixes only moved the error around; removing the field took it to 0 of 180 replays, and the live pair that followed
  was clean.
- **Never loosen a check to make a model pass.** Fix the instruction, or tighten the check.
- **AI answers are final.** Don't re-run until it looks right; a re-roll hides the failure rate you need to know.
