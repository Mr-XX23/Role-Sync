"""Credit metering for data-pipeline.

Contract: docs/billing/credit-system-api.md ("Internal" and "Python client rules").

- ``client``: talks to billing-service (credit check, usage charge, pending-usage retrier).
- ``metering``: collects the provider usage a unit of work spends (tokens, LlamaParse pages,
  Composio executions) while it runs, so it can be charged once at the end.
- ``charges``: builds the usage reports (operation, category, stable idempotency key).
- ``preflight``: the 402 refusal for user-started paid work, and the skip rule for background work.
- ``connectors``: meters connector sync runs and webhook processing.

Billing never breaks the work it meters: every call here swallows and logs its own failures.
"""
