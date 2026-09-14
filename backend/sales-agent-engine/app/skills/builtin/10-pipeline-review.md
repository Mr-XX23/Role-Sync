---
name: pipeline-review
description: Use when the rep wants their pipeline reviewed, which deals are at risk or stalled, and the next best action for each.
metadata:
  display_name: Pipeline review and stalled deals
  category: PIPELINE
  version: 1
  tools: [search_deals, recall, search_emails, list_calendar_events, update_deal, send_email]
---
# Pipeline review and stalled deals

Goal: a clear view of which deals need attention this week, and the next best action for each.

## Steps
1. List the rep's open deals with `search_deals`.
2. For each deal, check the activity: the last email with the company (`search_emails`), the next meeting (`list_calendar_events`), and known risks (`recall`).
3. Flag a deal as **at risk** when any of these is true: no contact for 14 days or more, the close date has passed or moved twice, there is no next step, no economic buyer is known, or a competitor is gaining ground.
4. Choose the next best action for each: book a meeting, send a useful follow-up, reach another contact in the account, move the close date, or close the deal as lost.

## Output
- One summary line: open deals, total value, how many are at risk, and what is expected to close this month.
- A table sorted by urgency: deal, stage, value, last activity, risk, next best action, due date.
- For each stalled deal, a short re-engagement email (under 80 words) that offers something useful.
- Suggested deal updates: stage, close date, next step.

Make changes (emails with `send_email`, deal updates with `update_deal`) only for the deals the rep chooses.
