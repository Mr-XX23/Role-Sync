---
name: quote-and-proposal
description: Use when the rep wants to price a solution, create a quote, or put together a proposal for a customer.
metadata:
  display_name: Quote and proposal
  category: CLOSE
  version: 1
  tools: [search_catalog, check_inventory, search_deals, recall, create_quote, generate_document, send_email]
---
# Quote and proposal

Goal: an accurate quote from the catalog, attached to the deal, with a short proposal the customer can say yes to.

## Steps
1. Confirm the requirements: products or services, quantities, term, any discount asked for, currency, validity, and who the quote is for. Ask the rep about anything missing.
2. Price only from the catalog: `search_catalog` for each item's price and discount limits, and `check_inventory` for physical stock.
3. Keep every discount within the item's maximum. If the rep wants more, say what the limit is and suggest trading value instead (a longer term, more volume, prepayment).
4. Find the deal with `search_deals`, then create the quote with `create_quote`, passing its `deal_id`. Reserve stock only if the rep asks.
5. If a proposal is wanted, write one to two pages with `generate_document`: their goals, the proposed solution, the price summary, why us (one proof point), the next steps and the validity.
6. Offer a short cover email with `send_email` that links the quote.

## Output
First the price breakdown (items, quantities, unit prices, discounts, total) for the rep to check. Then the quote, the proposal and the cover email, each as its own action for approval.
