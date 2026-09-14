---
name: personalized-outreach-sequence
description: Use when the rep wants to reach out to a new prospect, or re-engage a cold one, with a short series of personalized emails.
metadata:
  display_name: Personalized outreach sequence
  category: PROSPECT
  version: 1
  tools: [research_prospect, recall, search_emails, search_knowledge_base, search_catalog, send_email, remember]
---
# Personalized outreach sequence

Goal: three short emails that read as written for this person, each sent only when the rep approves it.

## Steps
1. Research first: `research_prospect` for the company and the person, `recall` about the account, and `search_emails` to make sure we are not already in touch.
2. Choose one relevant trigger (a hire, a launch, funding, an expansion, something they published) and the pain it likely creates.
3. Find proof: a result from a similar customer with `search_knowledge_base`, and the product that fits with `search_catalog`.
4. Write the sequence in the rep's voice, following their saved preferences:
   - **Email 1 (day 1)**: the trigger, the pain, one proof point and an easy question. Under 120 words.
   - **Email 2 (day 3 or 4)**: a different angle or a useful resource. Under 90 words.
   - **Email 3 (day 7 to 10)**: a polite close-the-loop with a simple yes-or-no question. Under 60 words.
   Give each a specific subject line. No attachments, no invented facts, no pressure tactics.
5. Show the rep all three first. Send only the email the rep asks for, with `send_email`; never send the whole sequence at once.
6. After sending, `remember` what was sent and when, so later follow-ups stay consistent.

## Output
The three emails, each with its day, subject and body, and one line on why this angle was chosen.
