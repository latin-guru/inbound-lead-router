# Northwind Lead Router (n8n inbound lead intake)

**Public showcase.** A consented lead comes in through a webhook, gets normalized and de-duplicated, is enriched, then receives a **rule-based** score and is routed as hot, warm, or cold.

Fictional company: **Northwind Solar Co-op**, a residential solar installer. All data is sample data (`example.com` emails). This is the companion automation to [support-ops-agent](https://github.com/latin-guru/support-ops-agent).

Built in **n8n**: Webhook → NormalizeLead → Data Table dedupe → Insert → HTTP mock enrichment → ScoreLead → Switch (hot / warm / cold) → Respond.

> Status: Intake, dedupe, enrichment, scoring, routing, and error alerts are complete. The live build accepted a sample "get a quote" lead at 100 / hot, returned `duplicate` on a replay of the same email, posted a Discord alert to `#automation-alerts` when enrichment was temporarily broken, and accepted a new lead at 100 / hot after the URL was restored.

## Architecture

```mermaid
flowchart LR
    F[Form / curl POST] --> W[Webhook POST /lead-intake]
    W --> N[NormalizeLead]
    N --> G[Get row in leads by email]
    G --> I{Email already seen?}
    I -->|yes| D[Respond 200 duplicate]
    I -->|no| INS[Insert row]
    INS --> H[HTTP Request<br/>mock enrichment + retry]
    H --> S[ScoreLead<br/>rule-based]
    S --> SW{Switch on tier}
    SW -->|hot| R[Respond 202 accepted]
    SW -->|warm| R
    SW -->|cold| R
    X[Error Trigger] -.->|optional| A[Discord #automation-alerts]
```

## What each step does

1. **Webhook** accepts JSON: `email`, `firstName`, `company`, `phone`, `formIntent`. Responds with a **Respond to Webhook** node (not "immediately"), so the caller gets a real status body.
2. **NormalizeLead** lowercases and trims the email and copies the other fields, plus a `receivedAt` timestamp.
3. **Get row(s)** looks up that email in the `leads` Data Table.
4. **If** the email already exists → **Respond 200** `{ "status": "duplicate", "email": "..." }` and stop. That keeps the table idempotent: the same lead posted twice does not create a second row.
5. **Insert row** stores the new lead (`status: new`). The phone column is written as text so values like `(555) 333-4444` are accepted.
6. **HTTP Request** calls a public mock enrichment API (`https://jsonplaceholder.typicode.com/users/1`) so the next step has a company name to work with. In the live build, Retry On Fail was turned on (3 tries, 2s wait).
7. **ScoreLead** applies documented rules (below) and sets `score` plus `tier`.
8. **Switch** branches on `hot` / `warm` / `cold`. All three branches return **202** `{ "status": "accepted", "email", "score", "tier" }`.

Hot / warm / cold branches are ready for later actions (Discord `#hot-leads`, a nurture table, a review table) without changing the scoring.

## Scoring rules (rule-based, not an ML model)

| Rule | Points |
|---|---|
| `formIntent` contains "quote" (case-insensitive) | +40 |
| A phone number is present | +25 |
| Enrichment returned a company name longer than 3 characters | +20 |
| An email is present | +15 |

| Total | Tier |
|---|---|
| 70 or more | hot |
| 40–69 | warm |
| under 40 | cold |

Example from the live build: `Maria.Lopez@Example.com`, phone present, `formIntent: "get a quote"`, enrichment company `Romaguera-Crona` → **score 100 / tier hot**.

A second post of the same email returns `{ "status": "duplicate" }` and does not insert again.


## Error alerts

This router uses the same `Northwind Error Alerts` workflow as [support-ops-agent](https://github.com/latin-guru/support-ops-agent). Import that workflow, publish it, and set it under **Settings → Error Workflow**. Escalations and system failures stay on separate Discord channels on purpose (`#support-escalations` vs `#automation-alerts`). The Discord webhook credential is not copied into this repo.

A dummy "Fetch Test Event" from n8n produces a placeholder alert (`Example Workflow`). A real failure needs a real broken step: in the live build the enrichment URL was temporarily pointed at a missing resource, a new sample email was posted, and the alert named **Northwind Lead Router**, failed step **HTTP Request**, and `The resource you are requesting could not be found` (Nov 6, 2026, 4:42 AM ET).

![Error workflow setting](docs/screenshots/error-workflow-settings.png)

![Failure alert in Discord after a broken enrichment URL](docs/screenshots/discord-error-alert.png)

## Test results

| Step | What was posted | Result |
|---|---|---|
| New lead | `maria.soto@example.com`, phone present, `formIntent: "request a quote"` | Accepted, score 100, tier hot |
| Replay | Same Maria email again | `{ "status": "duplicate" }` — no second row |
| Broken enrichment | `alex.nguyen@example.com` while the HTTP URL was invalid | Caller got `{ "message": "Error in workflow" }`; Discord `#automation-alerts` named Northwind Lead Router / HTTP Request / resource not found (4:42 AM ET) |
| Restored path | `jordan.lee@example.com` after the enrichment URL was put back | Accepted, score 100, tier hot |

Terminal proof (host URL, webhook path, and machine username covered):

![Terminal: duplicate, error, then accepted 100 / hot](docs/screenshots/terminal-test-results.png)

## Sample requests

Replace `YOUR_N8N_HOST` with your n8n instance. Use the **Listen for test event** URL while you are building (`/webhook-test/lead-intake`), then the production URL (`/webhook/lead-intake`) after you publish the workflow.

New lead (should accept and score hot):

```bash
curl -X POST 'https://YOUR_N8N_HOST/webhook-test/lead-intake' \
  -H 'Content-Type: application/json' \
  -d '{"email":"Maria.Lopez@Example.com","firstName":"Maria","company":"Summit Panels Inc","phone":"(555) 777-8888","formIntent":"get a quote"}'
```

Same email again (should return duplicate):

```bash
curl -X POST 'https://YOUR_N8N_HOST/webhook-test/lead-intake' \
  -H 'Content-Type: application/json' \
  -d '{"email":"Maria.Lopez@Example.com","firstName":"Maria","company":"Summit Panels Inc","phone":"(555) 777-8888","formIntent":"get a quote"}'
```

A weaker intent, for a warm or cold path:

```bash
curl -X POST 'https://YOUR_N8N_HOST/webhook-test/lead-intake' \
  -H 'Content-Type: application/json' \
  -d '{"email":"sam.review@example.com","firstName":"Sam","company":"","phone":"","formIntent":"just browsing"}'
```

## Setup

1. In n8n, create a Data Table named `leads` with text columns: `email`, `firstName`, `company`, `phone`, `formIntent`, `receivedAt`, `status`. Keep `phone` as text, not a number.
2. Import `workflows/northwind-lead-router.json`.
3. Open both Data Table nodes (**Get row(s)** and **Insert row**) and re-select the `leads` table (values marked `REPLACE_AFTER_IMPORT` on purpose).
4. Optional: turn on **Retry On Fail** on the HTTP Request node (3 tries, 2000 ms) if it is not already set.
5. Optional reliability: import `Northwind Error Alerts` from [support-ops-agent](https://github.com/latin-guru/support-ops-agent), publish it, and set it as this workflow's **Error Workflow**. Then temporarily break the enrichment URL, post a new sample email, and confirm an alert lands in `#automation-alerts`.
6. Listen for a test event, run one of the curl commands above, and confirm the response body.

The exported workflow was cleaned with `scripts/sanitize_workflow.py`: instance ID, workflow ID, webhook IDs/paths, project IDs and data-table IDs are removed.

## Honest limits / what I'd do next

- **Mock enrichment.** The HTTP call uses a public placeholder API, not a real company database. Production would use a real enrichment provider, with the same retry and error-workflow pattern.
- **Routing actions.** The Switch branches exist; they currently all return the same 202 body. Next step is a formatted Discord (or Slack) message for hot leads, a nurture table for warm, and a review table for cold, plus optional round-robin assignment to fake reps.
- **Error workflow.** Proven on this router with the shared `Northwind Error Alerts` workflow from the companion support-ops-agent repo (Settings → Error Workflow). A temporary bad enrichment URL produced `Error in workflow` for the caller and a Discord alert in `#automation-alerts` with the workflow name, failed step, and error text.
- **Validation.** Missing required fields are not yet rejected with a 400 / dead-letter row.
- **Sample scale.** Built on an n8n Cloud trial with a small Data Table of test leads.

## Contact
[LinkedIn: Kevin Gaviria](https://www.linkedin.com/in/kevin-gaviria)
