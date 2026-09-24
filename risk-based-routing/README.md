# Certificate Rotation 201: Risk-Based Routing

Coming soon. This demo extends 101 with:

- Risk scoring per certificate (low/medium/high)
- Switch-step routing to different approval flows per risk level
- Blast radius analysis
- Multiple hosts with different cert types

## Workflow

```mermaid
flowchart LR
  A[Cert expiry event] --> B[AI risk assessment]
  B --> C{Risk tier}
  C -->|Low| D[Auto-renew]
  C -->|Medium| E[Notify + renew]
  C -->|High| F[Approval required]
  D --> G[Validate TLS]
  E --> G
  F --> H[Run renewal after approval]
  H --> G
```

## Playbooks

🚧 **Under development** — playbook list and source links will be added when this demo is built.
