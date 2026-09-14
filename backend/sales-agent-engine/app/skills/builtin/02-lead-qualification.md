---
name: lead-qualification
description: Use when the rep asks whether a lead or deal is qualified, how strong it is, or what is missing to move it forward.
metadata:
  display_name: Lead qualification
  category: QUALIFY
  version: 1
  tools: [search_deals, recall, search_emails, read_email_thread, list_calendar_events, remember, update_deal]
---
# Lead qualification

Goal: an honest verdict on how qualified the opportunity is, what is missing, and the questions that close the gaps.

## Framework
Use MEDDICC, unless the rep or the workspace prefers BANT (budget, authority, need, timeline) for small, fast deals:
- **Metrics**: the measurable outcome the customer wants.
- **Economic buyer**: who signs, and whether we have spoken to them.
- **Decision criteria** and **decision process**: how they will choose, who is involved, and by when.
- **Identify pain**: the problem, what it costs them, and why it matters now.
- **Champion**: who argues for us inside the account.
- **Competition**: the alternatives, including doing nothing.

## Steps
1. Find the deal with `search_deals`, and `recall` what is known about the account and the deal.
2. Look for evidence in recent emails (`search_emails`, `read_email_thread`) and meetings (`list_calendar_events`).
3. Rate each element **Confirmed** (with the evidence), **Partial** or **Unknown**. Never mark something confirmed without evidence.
4. Save new evidence with `remember` about the deal.
5. If the rep asks, update the deal's next step or stage with `update_deal`.

## Output
- A one-line verdict: **Qualified**, **Needs work** or **Not qualified**, with the main reason.
- A table: element, status, evidence.
- The three biggest gaps, each with the exact question to ask and who to ask it.
- A recommended next step with a date.
