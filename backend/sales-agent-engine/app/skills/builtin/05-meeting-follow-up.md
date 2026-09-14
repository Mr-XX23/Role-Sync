---
name: meeting-follow-up
description: Use when a meeting or call just ended and the rep wants a recap email, agreed next steps and the deal brought up to date.
metadata:
  display_name: Meeting follow-up
  category: ENGAGE
  version: 1
  tools: [list_calendar_events, search_emails, recall, search_deals, send_email, update_deal, create_calendar_event, remember]
---
# Meeting follow-up

Goal: within a day of the meeting, the customer has a clear recap, the next steps are agreed, and our records match.

## Steps
1. Identify the meeting with `list_calendar_events`, and gather what was discussed: the rep's notes in this conversation, related `search_emails`, and `recall` about the account and deal.
2. If key facts are missing (decisions, owners, dates), ask the rep before writing. Never invent what was agreed.
3. Draft the recap email:
   - a thank-you line;
   - what we heard: their goals and pains, in their words;
   - what was agreed, with an owner and a date for every next step;
   - any materials we promised;
   - one clear call to action, such as confirming the next meeting.
4. Send it with `send_email` once the rep is happy with it.
5. Bring the deal up to date with `update_deal`: the stage if it moved, the next step, and the expected close date if it was discussed.
6. If a next meeting was agreed, propose it with `create_calendar_event`.
7. Save durable facts (decision makers, budget, timeline, objections) with `remember`.

## Output
The draft email first, then the deal changes and the proposed meeting, each as its own action for the rep to approve.
