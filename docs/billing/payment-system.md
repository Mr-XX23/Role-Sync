# billing-service — Payment System (Stripe)

New microservice: `backend/billing-service`. Spring Boot 4.1 / Java 25, own database
(`rolesync-micro-billing`), port **8085**, registered with Eureka, routed by the gateway at
`/api/v1/billing/**`.

This is the **payment** half of the billing system. The **credit** half (ledger, balances,
preflight/hold/settle) is the next slice — see
[cost-model-and-credit-system.md](cost-model-and-credit-system.md).

---

## What it does

```
User picks a package
        ↓
POST /api/v1/billing/checkout        (amount comes from OUR config, never the request)
        ↓
PaymentOrder row (CREATED → PENDING) + Stripe Checkout Session
        ↓
User pays on Stripe hosted page      (card data never touches our servers)
        ↓
Stripe → POST /api/v1/billing/webhooks/stripe   (HMAC-signed)
        ↓
PaymentOrder → SUCCEEDED  +  CreditGrant row (PENDING)
        ↓
[next slice] credit ledger drains PENDING grants → balance
```

### Why fulfilment is webhook-driven

The browser redirect to `success_url` is treated as **cosmetic**. A user can open that URL
directly, so it proves nothing. An order only becomes `SUCCEEDED` inside
`PaymentFulfillmentService`, driven by a signature-verified webhook.

---

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/billing/packages` | gateway JWT | Purchasable packages + enabled gateways |
| GET | `/api/v1/billing/health` | gateway JWT | Liveness + which providers are configured |
| POST | `/api/v1/billing/checkout` | gateway JWT | Start a purchase, returns `checkoutUrl` |
| GET | `/api/v1/billing/orders/{id}` | gateway JWT | Poll one order after the redirect |
| GET | `/api/v1/billing/orders` | gateway JWT | Recent purchase history |
| POST | `/api/v1/billing/webhooks/stripe` | **public + HMAC** | Stripe callback |

Identity comes from the gateway-injected `X-User-Id`; workspace from `X-Tenant-Id`
(or a `workspaceId` field/param as fallback).

**Checkout request** — note there is no amount field, by design:

```json
POST /api/v1/billing/checkout
Idempotency-Key: <optional, recommended>
{ "packageCode": "STARTER", "provider": "STRIPE" }
```

---

## Data model

| Table | Purpose |
|---|---|
| `payment_orders` | One purchase attempt. Snapshots credits + `amount_minor` at checkout, so a later price change never rewrites history. Unique on `idempotency_key`. |
| `payment_events` | Every verified webhook. **Unique on (provider, provider_event_id)** — this is the replay guard. Raw payloads are deliberately not stored (they carry customer contact details). |
| `credit_grants` | The money→credits seam. **Unique on `order_id`**, so a replayed webhook cannot grant twice. The credit ledger will consume `PENDING` rows. |

Money is always a `BIGINT` in the currency's **minor unit** (cents/paisa). Never a float.

---

## Security decisions

- **The client never sends a price.** `CheckoutService` reads credits and amount from
  configuration by `packageCode`. A caller cannot choose what it pays or receives.
- **Amount + currency are cross-checked on settlement.** If Stripe reports an amount that
  differs from the order, credits are **not** granted and the order is flagged for a human.
- **Hosted Checkout only.** Card details never reach our servers, keeping us out of PCI scope.
- **Raw body for signatures.** The webhook binds `@RequestBody String` because the HMAC
  covers the exact bytes; binding to a DTO would re-serialise and break verification.
- **Idempotent everywhere.** Stripe idempotency key on session creation; unique event id and
  unique grant-per-order on the way in.
- **Port 8085 is not published.** The service trusts `X-User-Id` only because the gateway
  verifies the RS256 cookie, strips client-supplied identity headers, and is the only route in.

### Known gaps (deliberate, for the next slice)

- **No workspace-membership check yet.** Order reads are scoped to `accountId` **and**
  `userId`, so no cross-workspace leak, but billing does not yet ask workspace-service
  whether the caller may buy for that workspace. Add this with the ledger.
- **Refund does not claw back credits.** `charge.refunded` moves the order to `REFUNDED` and
  logs a warning; reversing spent credits is a ledger decision, not a payment one.
- No invoices/receipts yet. No subscriptions — this is one-off credit top-ups only.

---

## Setup

### 1. Stripe test keys (you must do this — I cannot create the account)

1. Create an account at `dashboard.stripe.com` and stay in **Test mode** (free, no card needed).
2. Copy the **secret key** (`sk_test_...`) from Developers → API keys.
3. Get a **webhook signing secret** (`whsec_...`) — either from Developers → Webhooks, or from
   `stripe listen` (below), which prints one.

### 2. Add to `backend/.env`

```
BILLING_SERVER_PORT=8085
BILLING_SERVER_HOSTNAME=billing-service
JDBC_BILLING_DATABASE_URL=jdbc:postgresql://postgres:5432/rolesync-micro-billing
STRIPE_SECRET_KEY=sk_test_your_key_here
STRIPE_WEBHOOK_SECRET=whsec_your_secret_here
BILLING_SUCCESS_URL=http://localhost:5173/billing/success
BILLING_CANCEL_URL=http://localhost:5173/billing/cancel
```

**Also required** — `.env` already sets `GATEWAY_PUBLIC_PATHS`, and an env value overrides the
default in `gateway-service.properties`, so the webhook path must be added there or every
Stripe callback is rejected with 401:

```
GATEWAY_PUBLIC_PATHS=/api/v1/auth/,/api/v1/webhooks/,/api/v1/billing/webhooks/
```

### 3. Create the database

`init-db.sql` now creates `rolesync-micro-billing`, but that script only runs on a **fresh**
Postgres volume. On an existing volume, create it once by hand:

```bash
docker exec -i postgres psql -U postgres -c 'CREATE DATABASE "rolesync-micro-billing";'
```

### 4. Add the compose service

`backend/docker-compose.yml` is gitignored, so the service block could not be committed.
Append the block from [docker-compose.billing.yml](docker-compose.billing.yml) to it, then:

```bash
docker compose up -d --build billing-service
```

### 5. Restart the gateway and config server so they pick up the new route/config

```bash
docker compose restart config-service gateway-service
```

---

## Testing the flow locally

Stripe cannot reach `localhost`, so forward its webhooks with the Stripe CLI:

```bash
stripe listen --forward-to http://localhost:8080/api/v1/billing/webhooks/stripe
```

That prints a `whsec_...` — put it in `STRIPE_WEBHOOK_SECRET` and restart billing-service.

Then start a checkout, open the returned `checkoutUrl`, and pay with Stripe's documented test
card `4242 4242 4242 4242`, any future expiry, any CVC. Watch the order flip to `SUCCEEDED`
and a `credit_grants` row appear.

Replay-safety is worth checking too — `stripe events resend <event_id>` should leave exactly
one grant row.

---

## Adding eSewa and Khalti later

Implement `PaymentProvider` and register it as a `@Component`:

```java
PaymentProviderKey key();                                   // ESEWA / KHALTI
boolean isEnabled();                                        // credentials present
ProviderCheckout createCheckout(CheckoutCommand command);
WebhookOutcome parseWebhook(String rawBody, String sigHeader);
```

`PaymentProviderRegistry` picks it up automatically — **no controller or fulfilment change**,
because `WebhookOutcome` is already provider-neutral (`PAID / FAILED / EXPIRED / REFUNDED /
IGNORED`). Both are NPR-denominated, so add NPR packages (`price-minor` in paisa) rather than
converting USD at runtime. Note eSewa and Khalti verify by a signed/return-code callback rather
than an HMAC header, so `parseWebhook` for those will verify by calling the provider back.

## Tests

`mvn test` in `backend/billing-service` — 11 tests covering: price taken from config not the
caller, unknown package rejected, unwired provider rejected, workspace-namespaced idempotency
keys, credits granted exactly once, replayed event ignored, already-settled order not
re-granted, amount mismatch refused, currency mismatch refused, audit row written when no order
matches, expired checkout closed without granting.
