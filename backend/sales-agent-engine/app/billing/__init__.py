"""Credits: checking a workspace may start paid work, and charging what the work used.

- ``client``: the billing-service client (check, charge, the pending-usage retry queue).
- ``metering``: what is charged, hooked where all paid work passes (model router, Tavily, Composio).
- ``scope``: which workspace pays for the work running right now.

Contract: ``docs/billing/credit-system-api.md``.
"""
