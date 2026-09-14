# Credit system — API contract

Source of truth for billing-service, the Python metering clients and the frontend. Change this file
first if a contract has to move.

## Concepts

- **Credits belong to a workspace** (`X-Tenant-Id`). Members share one balance.
- **Welcome grant:** the first time billing sees a user in a workspace they **own**, that workspace
  receives **500 credits** (config `billing.credits.signup-grant`). Once per user, ever — creating more
  workspaces does not grant again, and being invited into someone else's workspace adds nothing there
  (otherwise inviting throwaway accounts would farm credits).
- **Precision:** the ledger stores **millicredits** (1 credit = 1,000). JSON exposes credits as numbers
  with up to 3 decimals, e.g. `487.235`. UIs show whole credits (floor).
- **Pricing:** billing-service turns reported usage into cost with a config rate card, then
  `millicredits = ceil(costUsd × (1 + buffer) ÷ costPerCredit × 1000)`, with `costPerCredit =
  creditPrice × (1 − targetMargin)` = $0.002 by default and buffer 15%.
- **Blocking:** a new paid operation is refused when balance ≤ 0 (`OUT_OF_CREDITS`) or the account is
  suspended (`CREDITS_SUSPENDED`). An operation already running finishes and is still charged, so a
  balance can dip below zero; the next purchase or grant pays it back.
- **Categories:** `AGENT`, `SEARCH`, `DOCUMENTS`, `CONNECTORS`, `CATALOG`, `OTHER`.

## Error shape

Java: `{"code": "OUT_OF_CREDITS", "error": "Your workspace is out of credits."}`
FastAPI: `HTTPException(402, detail={"code": "OUT_OF_CREDITS", "message": "..."})`

| Code | HTTP | Meaning |
|---|---|---|
| `OUT_OF_CREDITS` | 402 | balance ≤ 0 |
| `CREDITS_SUSPENDED` | 402 | a super admin suspended the workspace's credits |

The frontend treats **any 402** as "credits needed": refresh the balance, show the message, link to `/pricing`.

---

## Public — no login (gateway public path `/api/v1/billing/public/`)

### `GET /api/v1/billing/public/pricing`
```json
{
  "currency": "usd",
  "signupCredits": 500,
  "creditPriceUsd": 0.01,
  "packages": [
    {"code": "STARTER", "name": "Starter", "credits": 1000, "priceMinor": 1000, "currency": "usd"}
  ],
  "examples": [
    {"label": "Simple AI reply", "credits": 5},
    {"label": "Upload an 8-page PDF", "credits": 19}
  ]
}
```

---

## User — logged in (gateway injects `X-User-Id`; client sends `X-Tenant-Id`)

Every call checks the caller is a member of the workspace; otherwise **403**.

### `GET /api/v1/billing/credits`
Creates the account on first call and applies the welcome grant when due.
```json
{
  "workspaceId": "uuid",
  "balance": 487.235,
  "status": "ACTIVE",
  "lowBalance": false,
  "lowBalanceThreshold": 50,
  "lifetimeCredited": 500,
  "lifetimeUsed": 12.765
}
```
`status`: `ACTIVE` | `SUSPENDED`. `lifetimeCredited` = grants + purchases + admin additions.

### `GET /api/v1/billing/usage/summary?days=30`
```json
{
  "workspaceId": "uuid",
  "periodDays": 30,
  "from": "2026-08-16T00:00:00Z",
  "to": "2026-09-15T12:00:00Z",
  "balance": 487.235,
  "lifetimeCredited": 500,
  "lifetimeUsed": 12.765,
  "usedPercent": 2.55,
  "periodUsed": 12.765,
  "categories": [
    {"category": "AGENT", "label": "AI assistant", "credits": 10.2, "percent": 79.9},
    {"category": "DOCUMENTS", "label": "Documents", "credits": 2.565, "percent": 20.1}
  ]
}
```
`usedPercent` = lifetimeUsed ÷ lifetimeCredited × 100 (0–100, one decimal).
`categories[].percent` = share of `periodUsed`; every category is listed, zeros included.

### `GET /api/v1/billing/packages`
`{"packages": [...same shape as public...], "providers": ["STRIPE"]}`

### `POST /api/v1/billing/checkout`
Header `X-Tenant-Id`. Body `{"packageCode": "STARTER", "idempotencyKey": "optional, ≤100 chars"}`.
Browsers must send the key in the body: the gateway's CORS allow-list has no `Idempotency-Key`
header, so a browser preflight carrying it fails. Server-to-server callers may use the header instead.
Returns an order; redirect the browser to `checkoutUrl`.
```json
{"orderId": "uuid", "workspaceId": "uuid", "userId": "uuid", "packageCode": "STARTER", "credits": 1000, "amountMinor": 1000, "currency": "usd",
 "provider": "STRIPE", "status": "PENDING", "checkoutUrl": "https://checkout.stripe.com/...",
 "failureReason": null, "paidAt": null, "createdAt": "..."}
```
After payment Stripe returns to `{FRONTEND_URL}/billing/success?orderId={orderId}`; cancelling returns to
`{FRONTEND_URL}/pricing?checkout=cancelled`.

Errors: **403** `NOT_A_MEMBER`; **409** `CREDITS_SUSPENDED` while a super admin has suspended the workspace
(purchases pause; a checkout opened earlier still credits when it settles); **400** unknown package;
**502** Stripe refused the session.

### `POST /api/v1/billing/webhooks/stripe` (public, verified by `Stripe-Signature`)
Subscribe the Stripe endpoint (or `stripe listen`) to these events:

| Event | Effect |
|---|---|
| `checkout.session.completed` (payment_status `paid`), `checkout.session.async_payment_succeeded` | order `SUCCEEDED`, credits added once (amount and currency must match the order) |
| `payment_intent.payment_failed` | declined attempt noted; order stays `PENDING` so the buyer can retry |
| `checkout.session.async_payment_failed` | order `FAILED` |
| `checkout.session.expired` | order `EXPIRED` |
| `charge.refunded` | full refund: order `REFUNDED`, credits removed (balance may go negative); partial refund: noted for an admin |
| `charge.dispute.created` | workspace credits `SUSPENDED` until a super admin reactivates |

A paid event that arrives after the order was marked `FAILED`/`EXPIRED` still settles it: the money was taken.

### `GET /api/v1/billing/orders/{orderId}` · `GET /api/v1/billing/orders`
Order shape as above. Poll one order after returning from Stripe until `status` is `SUCCEEDED`
(credits added) or `FAILED` / `EXPIRED`. Reading a `PENDING` order also asks Stripe for its Checkout
Session (at most every 5 s per order), and a sweep does the same every minute, so a paid order settles
even when the webhook never arrives.

---

## Internal — service to service (`X-Internal-Token: $INTERNAL_SERVICE_TOKEN`)

Called directly at `http://billing-service:8085` (env `BILLING_SERVICE_URL`), never through the gateway.

### `GET /internal/v1/billing/credits/{workspaceId}/check?userId={uuid}`
```json
{"allowed": true, "code": "OK", "balance": 12.5, "status": "ACTIVE"}
```
`code`: `OK` | `OUT_OF_CREDITS` | `CREDITS_SUSPENDED`. Creates the account (and welcome grant) if needed.

### `POST /internal/v1/billing/usage`
```json
{
  "workspaceId": "uuid",
  "userId": "uuid or null",
  "operation": "agent.planner",
  "category": "AGENT",
  "idempotencyKey": "unique per charge; retries reuse it",
  "reference": "session / document / job id, optional",
  "items": [
    {"type": "TOKENS", "model": "gemini-3.5-flash", "inputTokens": 18000, "cachedInputTokens": 0, "outputTokens": 800},
    {"type": "UNITS", "unit": "LLAMAPARSE_PAGE", "quantity": 8}
  ],
  "metadata": {"free": "form"}
}
```
Response:
```json
{"creditsCharged": 13.225, "costUsd": 0.0231, "balance": 474.01, "status": "ACTIVE", "duplicate": false}
```
- Always records the charge, even if it takes the balance below zero or the account is suspended.
- Same `idempotencyKey` again → `duplicate: true`, nothing charged twice.
- `outputTokens` must include thinking tokens. Unknown models use the default rate.

**Units:** `LLAMAPARSE_PAGE`, `TAVILY_SEARCH`, `GROUNDED_PROMPT_25`, `GROUNDED_PROMPT_3X`, `COMPOSIO_EXECUTION`.

**Operation names** (free-form, but use these):

| Service | Operation | Category | Items |
|---|---|---|---|
| sales-agent-engine | `agent.model_call` | AGENT | TOKENS (every model call: planner, sub-agent, summary, brief, skill draft) |
| sales-agent-engine | `agent.web_answer` | SEARCH | TOKENS + `GROUNDED_PROMPT_25` or `_3X` |
| sales-agent-engine | `agent.web_search` | SEARCH | `TAVILY_SEARCH` |
| sales-agent-engine | `agent.connector_action` | CONNECTORS | `COMPOSIO_EXECUTION` |
| data-pipeline | `document.ingest` | DOCUMENTS (uploads, attachments, URLs) or CONNECTORS (synced items) | `LLAMAPARSE_PAGE` + TOKENS for scorer, classifier, embeddings |
| data-pipeline | `document.reclassify` | DOCUMENTS | TOKENS |
| data-pipeline | `knowledge.search` | SEARCH | TOKENS (query embedding) |
| data-pipeline | `catalog.ai` | CATALOG | TOKENS |
| data-pipeline | `connector.sync` | CONNECTORS | `COMPOSIO_EXECUTION` |

### Python client rules (both services)
- Env: `BILLING_SERVICE_URL` (default `http://billing-service:8085`), `INTERNAL_SERVICE_TOKEN`,
  `BILLING_ENABLED` (default `true`).
- **Check** before a user-started paid operation. `allowed=false` → 402 with the code and a message.
  Billing unreachable → **allow** and log (fail open).
- **Charge** after the work, with a stable idempotency key. If billing is unreachable, push the request to
  Redis list `billing:pending_usage` and retry it in the background (same key, so no double charge).
- **Background work** (auto-sync, reconciliation, webhook ingestion) skips a workspace whose check says
  `allowed=false` instead of failing.
- Never let a billing failure break the user's operation.

**Shared retry queue.** Both services use the same Redis list and each one's retrier sends the other's
entries, so the format and rules are part of this contract:
- Entry: `{"payload": <usage request body>, "attempts": n, "lastError": "...", "queuedAt": <epoch seconds>}`.
  New entries `LPUSH`; the retrier takes the oldest with `RPOP` and puts unsent ones back with `RPUSH`.
  A bare request body (no envelope) is accepted as `attempts: 0`.
- `POST /usage` answers: **2xx** → sent (a replay, including a same-key race, is `200` with
  `duplicate: true`). **5xx, 401, 403, 404, 408, 409, 425, 429** or no answer → keep it and retry later under
  the same key (401/403/404 cover a missing token or a service mid-deploy). **Any other 4xx** (400, 422) →
  the request itself is wrong: log it with the body and drop it.
- Retry every 30 s and give up after 720 attempts (about six hours, so a billing-service outage or bad
  deploy loses no charges); cap the list at 100,000 entries.

---

## Super admin (logged in + platform super admin via auth-service `platform-access`)

Base `/api/v1/billing/admin`. Non-admins get **403**.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/overview?days=30` | — | revenue, payments, credits sold/granted/used, provider cost, margin, accounts, usage by category, daily usage, top workspaces |
| GET | `/accounts?query=&status=&page=0&size=20` | — | `{items, page, size, total}` of accounts |
| GET | `/accounts/{workspaceId}` | — | account + recent transactions + usage by category |
| POST | `/accounts/{workspaceId}/grant` | `{"credits": 100, "reason": "..."}` | account |
| POST | `/accounts/{workspaceId}/deduct` | `{"credits": 50, "reason": "...", "allowNegative": false}` | account |
| POST | `/accounts/{workspaceId}/suspend` | `{"reason": "..."}` | account |
| POST | `/accounts/{workspaceId}/reactivate` | `{"reason": "..."}` | account |
| GET | `/payments?status=&page=0&size=20` | — | `{items, page, size, total}` of orders |
| GET | `/usage?days=30&workspaceId=` | — | usage by category, by operation and by model |

**Account shape:**
```json
{"workspaceId": "uuid", "balance": 487.235, "status": "ACTIVE", "lifetimeCredited": 500,
 "lifetimeUsed": 12.765, "lifetimePurchased": 0, "suspendedReason": null,
 "lastActivityAt": "...", "createdAt": "..."}
```
**Transaction shape:**
```json
{"id": "uuid", "type": "USAGE", "credits": -13.225, "balanceAfter": 474.01, "operation": "agent.model_call",
 "category": "AGENT", "reason": null, "actorUserId": null, "reference": "...", "createdAt": "..."}
```
`type`: `WELCOME_GRANT` | `PURCHASE` | `ADMIN_GRANT` | `ADMIN_DEDUCT` | `USAGE` | `REFUND_CLAWBACK` |
`ACCOUNT_SUSPENDED` | `ACCOUNT_REACTIVATED` (status changes, 0 credits).
Rules: grant/deduct amounts must be > 0 and ≤ 1,000,000 credits; a reason is required; deduct beyond the
balance needs `allowNegative: true`, otherwise **409**. Every admin action records the admin's user id.
