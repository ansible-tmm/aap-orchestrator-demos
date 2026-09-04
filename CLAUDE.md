# AI assistant guide — aap-orchestrator-demos

Context for Claude, Cursor, and other AI coding tools working in this repository.

## Demo marketplace layout

The GitHub Pages site (`index.html` + `_data/demos.yml`) has two card sections:

| Section | Grid | Purpose |
|---|---|---|
| **Featured** | 3 columns (`card-grid--featured`) | Hero demos — largest visual presence |
| **All demos** | Auto-fill, smaller cards | Full catalog |

Within **All demos**, cards render **active** demos first (in `demos.yml` order), then **coming soon**.

## Featured card limit: exactly 3

The Featured section uses a **3-column grid**. Only **three** demos may have `featured: true` at a time.

- Adding a fourth featured demo breaks the layout (orphan row, uneven grid).
- Before setting `featured: true` on a new demo, set `featured: false` on an existing featured demo.
- Demos moved out of Featured stay in the catalog under **All demos**. Put them near the top of `demos.yml` among active entries if they should appear first in the smaller grid.

### Current featured demos

1. **RHEL CVE Remediation** (`cve-remediation`)
2. **Intelligent Cert Lifecycle** (`cert-lifecycle`)
3. **Ticket Enrichment** (`ticket-enrichment`)

### Not featured (example)

**Disk Utilization & Remediation** (`disk-utilization`) is active but not featured — it leads the **All demos** grid.

## Where to edit

| Change | File |
|---|---|
| Featured flag, title, blurb, status | `_data/demos.yml` |
| Detail page copy, building blocks | `_data/demo_pages.yml` |
| Card sort order (active vs coming soon) | `index.html` |
| Featured / All demos section markup | `index.html` |

## Related rules

- `.cursor/rules/demo-featured-cards.mdc` — featured limit and marketplace layout
- `.cursor/rules/demo-site-copy.mdc` — CTA labels and playbook tables
- `.cursor/rules/automation-orchestrator-naming.mdc` — automation orchestrator naming
