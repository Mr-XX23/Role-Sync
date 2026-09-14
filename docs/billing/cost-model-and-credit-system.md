# Role-Sync — Cost Model & Credit System (v2)

> **Status:** analysis for sign-off, verified against the code on 2026-09-15. Supersedes v1 (2026-09-12).
> Every figure is produced by [`tools/economics_v2.py`](tools/economics_v2.py); change an input there and
> re-run rather than editing numbers by hand. No credit code exists yet. The Stripe payment service is
> on branch `feat/billing-payment-stripe` (not merged).

---

## 1. The answers

| Question | Answer |
|---|---|
| What does one agent message cost us? | **$0.110** on today's model (`gemini-3.5-flash`, no caching). **$0.023** on the recommended routing (§5). Averaged over simple, tool, research and heavy turns. |
| What is one credit? | **$0.01** to the user. An action consumes `ceil(actual cost × 1.15 ÷ $0.002)` credits, so each credit is backed by at most **$0.00174** of real cost — **82.6% gross margin at list price**, before payment fees. |
| How many credits does a message use? | **~14** on the recommended routing (5 simple · 10 tool · 51 research · 66 heavy). **64** on today's model. |
| What should users pay? | **Free** $0 (300 credits/month) · **Starter $19** (2,500) · **Pro $49** (7,500) · **Business $149** (25,000). Top-up packs: 1,000 for $10, 5,000 for $45, 20,000 for $160. |
| What profit do we make? | **66–80%** gross margin per plan after Stripe fees. Scenario profit margin **61%** at launch, **67%** at growth. |
| What do free users get? | **500 welcome credits + 300 credits every month.** Worst case costs us **$1.39** in month one and **$0.52/month** after. One Starter customer pays for ~58 free workspaces. |
| When do we break even? | Launch servers ($22/month) = **2 Starter** customers. Growth stack ($250/month) = **7 Pro** or **17 Starter**. |
| The one decision that matters | **Move the agent's planner off `gemini-3.5-flash`.** On today's model Starter's 2,500 credits buy ~39 messages; on the recommended routing, ~180. Margin is protected either way (metered billing); value to the user is not. |

---

## 2. Two regimes: free tiers today, paid tiers later

**Today** Gemini runs on its free tier, OpenRouter `:free` models serve the classifier, catalog AI and the
agent's simple route, and LlamaParse (10k credits/month ≈ 3,300 pages), Composio (20k executions),
Tavily (1k searches) and LangSmith (5k traces) sit inside free allowances. Real monthly spend is
roughly the server.

**Everything in this document is priced at paid rates**, because free tiers cannot carry customers:

- OpenRouter's free models share **one 50-requests-per-day cap** across the classifier, catalog AI and the
  agent — the first active team exhausts it.
- **Gemini's free tier may use prompts to improve Google's products.** Customer emails, deals and documents
  should not flow through it.
- Free-tier rate limits throttle paying users at exactly the wrong moment.

Treat the free period as runway, not margin. Upgrade before onboarding paying customers.

---

## 3. What changed since v1 (verified in code, 2026-09-15)

| Area | v1 | Now |
|---|---|---|
| Tools sent to the planner on every step | 33 | **50 tools, 56 schemas ≈ 15.3k tokens** (measured) |
| Fixed input tokens per planning step | 8–12k | **~18k** — system prompt 1.6k + tool definitions 15.3k + profile and skill list 1.1k |
| Chat attachments | — | Up to **2 files × 25 MB** per message. They are uploaded to the Knowledge Vault, run the full ingestion pipeline, then the agent reads them back with its knowledge-base tools. |
| Gatekeeper semantic scorer | not implemented | **On by default**, `gemini-3.5-flash-lite`, scores every ingested item (uploads, attachments, each synced email, message, page, event) |
| Embeddings | `gemini-embedding-001`, $0.15/M | **`gemini-embedding-2`, $0.20/M**; child chunks embedded with 12% overlap |
| Reconciliation | off | **On, nightly**, Composio listings for Drive, Notion and Calendar |
| Skills | — | Listed in the prompt; full text loads only through `use_skill`; AI drafting capped at 20 per rep per day |
| Plans | — | `PlatformPlan` exists with `priceMonthlyCents`, `maxMembers`, `agentTokensPerDay`, `maxConcurrentAgentRuns` |
| Reindex double-parse | leaked a LlamaParse charge | reuses stored text |
| Hardcoded Composio key | in source | removed — still in git history, so **rotate it** |
| Token metering | planner + sub-agents | unchanged. Provider usage (input, output, thinking) is already captured on every call. |

---

## 4. Vendor prices (verified September 2026)

| Service | Unit | Price |
|---|---|---|
| `gemini-3.5-flash` | per 1M input / output / cached input | $1.50 / $9.00 / $0.15 |
| `gemini-3.5-flash-lite` | per 1M | $0.30 / $2.50 / $0.03 |
| `gemini-2.5-flash` | per 1M | $0.30 / $2.50 / $0.03 |
| `gemini-2.5-flash-lite` | per 1M | $0.10 / $0.40 / $0.01 |
| `gemini-embedding-2` | per 1M text tokens | $0.20 (batch $0.10) |
| Google Search grounding | per grounded prompt | 2.5 models: $0.035 after 500/day free · 3.x models: $0.014 after 5,000/month free |
| LlamaParse | per page, default tier | ~$0.00375 · 10k credits/month free |
| Composio | per tool execution | $0.004 · 20k/month free · Pro $29 for 50k |
| Tavily | per basic search | $0.008 · 1k/month free |
| LangSmith | per trace | $0.0025 beyond 5k/month · Plus $39/seat |
| Twilio SMS | per US A2P segment | ~$0.0125 |
| Stripe | per payment | 2.9% + $0.30 · **international cards 4.4% + $0.30** · +1% currency conversion |
| Hetzner CX43 | 8 vCPU · 16 GB · 160 GB | €15.99/month, +20% for backups (after the June 2026 price rise) |

Thinking tokens bill as output. Images count 258 tokens per 768 px tile.

---

## 5. Anatomy of an agent message

Each planning step sends **~18k tokens before any conversation**. A turn repeats that for every step
(up to 18), adds conversation history and tool results (capped at 48k per call, summarised beyond),
and adds output — which is **not capped** on the planner.

| Turn | Steps | Today's model | Credits | Recommended routing | Credits |
|---|---:|---:|---:|---:|---:|
| Simple chat reply | 1 | $0.034 | 20 | $0.007 | 5 |
| Tool turn (look something up, answer) | 3 | $0.121 | 70 | $0.016 | 10 |
| Research turn (web search + prospect research) | 4 | $0.284 | 164 | $0.087 | 51 |
| Heavy turn (8 steps, 2 searches) | 8 | $0.569 | 328 | $0.114 | 66 |
| **Blended message** (50 / 35 / 12 / 3%) | | **$0.110** | **64** | **$0.023** | **14** |

**Recommended routing** = `gemini-3.5-flash-lite` as the planner, the stable prompt prefix served from
Gemini's cache from the second step of a turn, and 3.x Google Search grounding.

Because agent turns are billed on the tokens the provider actually reports, these are what users pay —
not estimates the business absorbs if wrong.

---

## 6. Cost of every action (recommended routing)

| Area | Action | Our cost | Credits | Note |
|---|---|---:|---:|---|
| Agent | Simple chat reply | $0.0072 | 5 | $0.034 on today's model |
| Agent | Tool turn | $0.0161 | 10 | $0.121 on today's model |
| Agent | Research turn | $0.0871 | 51 | $0.284 on today's model |
| Agent | Heavy turn | $0.1143 | 66 | $0.569 on today's model |
| Agent | Web search (inside a turn) | $0.0233 | 14 | $0.044 with 2.5 grounding |
| Agent | Prospect research (inside a turn) | $0.0403 | 24 | $0.061 today |
| Agent | Draft a skill with AI | $0.0056 | 4 | $0.021 on 3.5 Flash |
| Agent | Send an email / Slack message, create an event | $0.0040 | 3 | one Composio execution, plus the turn |
| Knowledge | Upload an 8-page PDF or Office file | $0.0326 | 19 | parse $0.030 · score $0.0007 · classify $0.0006 · embed $0.0013 |
| Knowledge | Upload a 50-page PDF | $0.1972 | 114 | parsing is ~95% |
| Knowledge | Upload a text, CSV or Markdown file | $0.0019 | 2 | parsed locally |
| Knowledge | Chat image attachment | $0.0048 | 3 | OCR as one LlamaParse page |
| Knowledge | Reclassify a document | $0.0005 | 1 | free today (`openrouter/free`) |
| Knowledge | Semantic search query | < $0.0001 | free | rate-limit instead of charging |
| Catalog | AI catalog search | < $0.0001 | free | rate-limit instead of charging |
| Catalog | Generate findability for a product | $0.0004 | 1 | free today |
| Catalog | Catalog, inventory, deals, quotes, documents | $0 | free | database only |
| Connectors | Gmail sync run (10 emails) | $0.0092 | 6 | one Composio call; each email scored and embedded |
| Connectors | Drive sync (20 files × 5 pages) | $0.5013 | 289 | one download per file; parsing dominates |
| Connectors | Nightly reconciliation per connected user | $0.0120 | overhead | ≈ $0.36/month; price into plans, don't charge |
| Platform | Signup with phone OTP | $0.0125 | overhead | only when a phone number is used |
| Platform | Invite or verification email | $0 | — | Gmail SMTP, 500/day cap |
| Platform | LangSmith trace (per traced turn) | $0.0025 | overhead | beyond 5k/month; sample in production |

**Heaviest surfaces:** research turns (search fees) and file-heavy connector syncs (parsing). Gate Drive
auto-sync by plan and charge parsed pages in credits.

---

## 7. Fixed monthly costs

| | Launch | Growth |
|---|---:|---:|
| Server | Hetzner CX43 + backups ≈ $21 | CPX42 + backups ≈ $91 |
| Domain | ~$1 | ~$1 |
| Composio | free (20k executions) | $29 |
| LlamaParse | free (10k credits) | $50 |
| Tavily | free (1k searches) | $30 |
| LangSmith | free (5k traces) or off | $39, or off |
| Transactional email | Gmail SMTP | ~$10 |
| **Total** | **~$22** | **~$250** |

Measured footprint: the 13 containers use **~2.8 GB RAM** together (+~0.4 GB for billing-service), so a
16 GB server has room. Hetzner raised CPX and CCX prices 2–3× in June 2026; size on the cost-optimised CX
line first.

---

## 8. The credit unit and how charging works

- **1 credit = $0.01** at list price.
- **Metered actions** (agent turns, any model call): `credits = ceil(actual_cost × 1.15 ÷ 0.002)`, where
  `actual_cost` = reported input, cached input and output (including thinking) tokens × the rate valid
  at that moment for that model.
- **Flat actions** (parsed page, ingested item, web search, Composio execution): credits from a config
  table, seeded with §6.
- **Preflight → hold → settle:** estimate before a turn starts (18k × expected steps + history), refuse if
  the balance cannot cover the hold, then settle to the actual cost and release the rest.
- **Rates are data, not code:** effective-dated `provider_rates` and `operation_costs`, so historical usage
  keeps the price it was charged at.

---

## 9. Plans, packs and margins

**Model:** every workspace is on a plan — the existing `PlatformPlan` — that includes monthly credits.
Stripe credit packs top up. Credits are pooled per workspace.

| Plan | Price | Credits / month | Members | Stripe fee | Our cost if all used | Typical (60%) | Margin, all used | Margin, typical |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Free | $0 | 300 | 1 | — | $0.52 | $0.31 | — | — |
| Starter | $19 | 2,500 | 3 | $1.14 | $4.35 | $2.61 | 71% | 80% |
| Pro | $49 | 7,500 | 10 | $2.46 | $13.04 | $7.83 | 68% | 79% |
| Business | $149 | 25,000 | 30 | $6.86 | $43.48 | $26.09 | 66% | 78% |

| Pack | Price | Per credit | Stripe fee | Our cost | Margin |
|---:|---:|---:|---:|---:|---:|
| 1,000 | $10 | $0.0100 | $0.74 | $1.74 | 75% |
| 5,000 | $45 | $0.0090 | $2.28 | $8.70 | 76% |
| 20,000 | $160 | $0.0080 | $7.34 | $34.78 | 74% |

Fees use Stripe's international card rate. **Keep every payment at $10 or more** — the $0.30 fixed fee
takes 7.4% of a $10 payment and 10% of a $5 one.

**Margin lever:** these prices target 80% margin. At a 70% target the blended message drops from ~14 to
~9 credits, and Starter buys ~280 messages instead of ~180.

---

## 10. The free plan

**Grant:** 500 welcome credits when the workspace is created, then 300 credits every month (no rollover).

**Cost ceiling:** $1.39 in month one, $0.52/month after (≈ $0.26 at half use).

**Enough for:** ~50 agent messages, 5 documents and a Gmail sync in the first month (800 credits).

| Included | Limited | Paid plans only |
|---|---|---|
| Agent chat on the cheapest planner | Web search and prospect research: 10 / month | Sending email or Slack messages, creating events, through the agent (spam risk, not cost) |
| Knowledge Vault: upload, search, read | Document parsing: charged in credits | Drive, Slack and Notion connectors |
| Catalog, inventory, deals, quotes, documents | AI skill drafting: 3 / day | Auto-sync and nightly reconciliation |
| Memory; using skills | Gmail and Calendar: read-only, manual sync | More than 1 member or 1 concurrent run |

**Abuse controls:** credits only after email verification; the grant belongs to the workspace, not each
member; a plan `agentTokensPerDay` cap (e.g. 150k) on top of the existing 10 turns/minute; no phone OTP
required (saves $0.0125 per signup).

---

## 11. Unit economics

| Scenario | Free workspaces | Starter | Pro | Business | Revenue | Stripe fees | AI cost | Fixed | Profit | Margin |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Launch | 50 | 5 | 2 | 0 | $193 | $11 | $42 | $22 | **$119** | 61% |
| Early traction | 150 | 15 | 6 | 1 | $828 | $43 | $171 | $82 | **$532** | 64% |
| Growth | 300 | 40 | 20 | 5 | $2,885 | $147 | $547 | $250 | **$1,941** | 67% |

Assumptions: free workspaces use half their grant; paid plans use 60% of included credits; pack revenue of
$0 / $100 / $400 is fully consumed.

**Break-even:** a Starter customer grosses $15.26 a month, a Pro customer $38.72. Launch fixed costs need
**2 Starter** customers; the growth stack needs **7 Pro** or **17 Starter**.

---

## 12. Cost levers, in order of money saved

1. **Planner → `gemini-3.5-flash-lite`**, keeping 3.5 Flash for escalation — **4.8× cheaper per message**.
2. **Tool definitions are 15.3k tokens on every step.** Bind tool groups by intent (catalog, email,
   knowledge) — roughly halves fixed input.
3. **Prompt caching:** cached input costs 10% of the normal price. The clock already sits at the end of the
   system prompt; move it into the user turn so the whole 18k prefix can cache.
4. **Cap planner and sub-agent output** and use a low thinking level for routine steps — thinking bills as
   output.
5. **Ground searches on 3.x** ($0.014) instead of 2.5 ($0.035). The 429s seen on 3.x were on the free tier;
   re-test on paid.
6. **Meter the unmetered calls:** grounded answers, prospect briefs, summaries and skill drafts.
7. **Replace OpenRouter `:free` routes** with paid models before launch (50/day shared cap).
8. **LangSmith:** sample or disable in production.
9. **Embeddings through the async Batch API** (50% off) for bulk ingestion.
10. **Rotate the Composio key.**

---

## 13. Build plan (after sign-off)

1. **billing-service** — merge the Stripe work onto current `main`; add an append-only, idempotent,
   workspace-scoped credit ledger with balances and holds; usage events; effective-dated pricing config;
   plan credit grants (monthly job and welcome grant); Stripe subscriptions for plans plus one-off packs.
2. **Internal charging API** (`X-Internal-Token`) — preflight/hold, settle, flat charge, refund.
3. **sales-agent-engine** — hold before a turn, settle actual tokens for every model call (including
   today's unmetered ones), refuse on insufficient credits, gate tools by plan.
4. **data-pipeline** — charge per parsed page, per ingested item and per connector sync.
5. **workspace-service** — add `monthlyCredits` and free-plan entitlements to `PlatformPlan`; let super
   admins grant and adjust credits.
6. **Frontend** — balance, plans and pricing page, Stripe checkout, usage history, out-of-credits state.

---

## Appendix: assumptions

- 3.5 characters per token (the engine's own estimate). Output per step, including thinking: 600 for a
  simple reply, 800 for tool and research steps, 1,000 for heavy turns.
- Message mix: 50% simple, 35% tool, 12% research, 3% heavy.
- A typical 8-page document ≈ 6,000 tokens; an email ≈ 500 tokens.
- Caching assumes the 18k prefix is served from cache from the second step of a turn. Gemini's implicit
  caching is automatic but not guaranteed.
- Every payment uses Stripe's international card rate.
- Once real traffic exists, replace these assumptions with measured usage from the billing usage events.
