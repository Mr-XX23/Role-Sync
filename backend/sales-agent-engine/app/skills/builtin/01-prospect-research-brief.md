---
name: prospect-research-brief
description: Use when the rep wants to research a company or a contact before reaching out, a call or a meeting.
metadata:
  display_name: Prospect research brief
  category: PROSPECT
  version: 1
  tools: [research_prospect, web_search, recall, search_deals, search_emails, search_knowledge_base, search_catalog, remember]
---
# Prospect research brief

Goal: a short, cited brief the rep can read in two minutes before contacting the prospect.

## Steps
1. Confirm who. If the company name is ambiguous, pick the most likely match and say which one you chose.
2. Gather in one round, all at once:
   - `research_prospect` for the company (and the person, if named): what they do, size, recent news, funding, leadership changes, hiring, launches.
   - `recall` about the account, and `search_deals` for any open or past deal with them.
   - `search_emails` for earlier conversations with the company.
   - `search_knowledge_base` for case studies in their industry and battlecards for competitors they use.
3. Match their likely needs to what we sell with `search_catalog`: the one to three products that fit best.
4. Save durable facts you learned (key people and roles, stated needs, competitors in use) with `remember` about the account.

## Output
- **Snapshot**: one or two lines on what they do, their size and market.
- **Why now**: two to four recent triggers (news, hires, funding, expansion), each with a date and a link.
- **People**: the likely economic buyer and champion, with their roles.
- **Likely pains and how we help**: each pain mapped to a product or a case study.
- **History with us**: past emails, deals, and anything promised or quoted.
- **Talking points** for the first conversation, and one question to open with.

Cite web facts with their links. Say plainly when something could not be found, and never guess numbers.
