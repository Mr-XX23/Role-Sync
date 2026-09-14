"""Role-Sync unit economics v2 — every number in the cost model comes from here.

Inputs are the code facts verified on 2026-09-15 and vendor prices verified the same
week. Run: python economics_v2.py > economics_v2.md
"""
import math

# ---------------------------------------------------------------- vendor prices
# USD per 1M tokens: (input, output, cached input)
MODEL = {
    "gemini-3.5-flash": (1.50, 9.00, 0.15),
    "gemini-3.5-flash-lite": (0.30, 2.50, 0.03),
    "gemini-2.5-flash": (0.30, 2.50, 0.03),
    "gemini-2.5-flash-lite": (0.10, 0.40, 0.01),
}
EMBED_2 = 0.20            # gemini-embedding-2, per 1M text tokens
GROUND_25 = 0.035         # per grounded prompt, Gemini 2.5 (after 500/day free)
GROUND_3X = 0.014         # per grounded prompt, Gemini 3.x (after 5,000/month free)
TAVILY = 0.008            # per basic search
LLAMA_PAGE = 0.00375      # LlamaParse default tier, per page
COMPOSIO = 0.004          # per tool execution (overage)
SMS = 0.0125              # Twilio US A2P segment
TRACE = 0.0025            # LangSmith base trace beyond the free 5k/month

# ---------------------------------------------------------------- code facts
FIXED_PER_STEP = 18_000   # system prompt ~1.6k + 56 tool schemas ~15.3k + profile/skills ~1.1k
CHARS_PER_TOKEN = 3.5

# ---------------------------------------------------------------- credit rules
CREDIT_PRICE = 0.01       # list price of one credit
TARGET_MARGIN = 0.80
BUFFER = 0.15
COST_PER_CREDIT = CREDIT_PRICE * (1 - TARGET_MARGIN)          # 0.002
COST_BACKING_ONE_CREDIT = COST_PER_CREDIT / (1 + BUFFER)       # ~0.00174


def credits(cost):
    return max(1, math.ceil(cost * (1 + BUFFER) / COST_PER_CREDIT)) if cost > 0 else 0


def tok(model, inp, out, cached=0):
    pin, pout, pcache = MODEL[model]
    return ((inp - cached) * pin + cached * pcache + out * pout) / 1e6


# ---------------------------------------------------------------- agent turns
TURNS = {
    # name: (planner steps, history tokens per step, output tokens per step, web searches, prospect researches)
    "Simple chat reply": (1, [1_000], 600, 0, 0),
    "Tool turn (look something up, answer)": (3, [1_000, 4_000, 7_000], 800, 0, 0),
    "Research turn (web + prospect)": (4, [1_000, 5_000, 9_000, 13_000], 800, 1, 1),
    "Heavy turn (8 steps, 2 searches)": (8, [2_000, 6_000, 10_000, 14_000, 18_000, 22_000, 26_000, 30_000], 1_000, 2, 0),
}

CONFIGS = {
    "current": dict(planner="gemini-3.5-flash", cache=False, ground=GROUND_25, brief="gemini-2.5-flash-lite"),
    "recommended": dict(planner="gemini-3.5-flash-lite", cache=True, ground=GROUND_3X, brief="gemini-2.5-flash-lite"),
}


def web_search(cfg):
    return TAVILY + cfg["ground"] + tok("gemini-2.5-flash", 2_000, 300)


def prospect(cfg):
    return 3 * TAVILY + cfg["ground"] + tok("gemini-2.5-flash", 2_000, 300) + tok(cfg["brief"], 6_000, 900)


def turn_cost(cfg, steps, history, out, searches, prospects):
    total = 0.0
    for i in range(steps):
        cached = FIXED_PER_STEP if (cfg["cache"] and i > 0) else 0
        total += tok(cfg["planner"], FIXED_PER_STEP + history[i], out, cached=cached)
    total += searches * web_search(cfg) + prospects * prospect(cfg)
    return total


def turn_table():
    rows = []
    for name, spec in TURNS.items():
        cur = turn_cost(CONFIGS["current"], *spec)
        rec = turn_cost(CONFIGS["recommended"], *spec)
        rows.append((name, cur, credits(cur), rec, credits(rec)))
    return rows


BLEND = {  # share of agent messages by kind
    "Simple chat reply": 0.50,
    "Tool turn (look something up, answer)": 0.35,
    "Research turn (web + prospect)": 0.12,
    "Heavy turn (8 steps, 2 searches)": 0.03,
}


def blended(config):
    cost = sum(BLEND[n] * turn_cost(CONFIGS[config], *TURNS[n]) for n in TURNS)
    return cost, credits(cost)


# ---------------------------------------------------------------- ingestion & other actions
def doc_cost(pages, tokens_text, parsed=True):
    parse = pages * LLAMA_PAGE if parsed else 0.0
    scorer = tok("gemini-3.5-flash-lite", min(tokens_text, 4_000 / CHARS_PER_TOKEN) + 200, 100)
    classify = tok("gemini-2.5-flash-lite", 4_500, 150) + tok("gemini-2.5-flash-lite", 520, 150)
    embed = tokens_text * 1.12 * EMBED_2 / 1e6
    return parse, scorer, classify, embed


def email_item(tokens_text=500):
    return tok("gemini-3.5-flash-lite", tokens_text + 200, 80) + tokens_text * 1.12 * EMBED_2 / 1e6


ACTIONS = []


def add(group, name, cost, note):
    ACTIONS.append((group, name, cost, credits(cost), note))


rec = CONFIGS["recommended"]
cur = CONFIGS["current"]
for name, spec in TURNS.items():
    add("Agent", name, turn_cost(rec, *spec), f"on today's model: ${turn_cost(cur, *spec):.3f}")
add("Agent", "Web search (inside a turn)", web_search(rec), f"2.5 grounding today: ${web_search(cur):.3f}")
add("Agent", "Prospect research (inside a turn)", prospect(rec), f"today: ${prospect(cur):.3f}")
add("Agent", "Draft a skill with AI", tok("gemini-3.5-flash-lite", 2_000, 2_000), f"on 3.5 Flash: ${tok('gemini-3.5-flash', 2_000, 2_000):.3f}; capped 20/rep/day")
add("Agent", "Agent sends an email / Slack message / creates an event", COMPOSIO, "one Composio execution, plus the turn itself")

p, s, c, e = doc_cost(8, 6_000)
add("Knowledge", "Upload an 8-page PDF / Office doc", p + s + c + e, f"parse ${p:.4f} · score ${s:.4f} · classify ${c:.4f} · embed ${e:.4f}")
p, s, c, e = doc_cost(50, 37_500)
add("Knowledge", "Upload a 50-page PDF", p + s + c + e, "parsing is ~95% of it")
p, s, c, e = doc_cost(0, 3_000, parsed=False)
add("Knowledge", "Upload a text / CSV / Markdown file", p + s + c + e, "parsed locally, no LlamaParse")
p, s, c, e = doc_cost(1, 300)
add("Knowledge", "Chat image attachment", p + s + c + e, "OCR as one LlamaParse page")
add("Knowledge", "Reclassify a document", tok("gemini-2.5-flash-lite", 4_500, 150), "free today (openrouter/free)")
add("Knowledge", "Semantic search query", 40 * EMBED_2 / 1e6, "one query embedding")
add("Catalog", "AI catalog search (query expansion)", tok("gemini-2.5-flash-lite", 190, 60), "free today")
add("Catalog", "Generate findability for a product", tok("gemini-2.5-flash-lite", 1_150, 800), "free today")
add("Catalog", "Catalog / inventory / deals / quotes tools", 0.0, "database only - no paid API")
add("Connectors", "Gmail sync run (10 emails)", COMPOSIO + 10 * email_item(), "1 Composio call + score & embed each email")
add("Connectors", "Drive sync (20 files, 5 pages each)", COMPOSIO * 21 + 20 * sum(doc_cost(5, 3_750)), "one download per file")
add("Connectors", "Nightly reconciliation, per connected user", 3 * COMPOSIO, "gdrive + notion + calendar listings")
add("Platform", "Signup with phone OTP", SMS, "only if a phone number is used")
add("Platform", "Invite a teammate / verification email", 0.0, "Gmail SMTP (500/day cap)")
add("Platform", "LangSmith trace (per traced turn)", TRACE, "beyond 5k/month free")

# ---------------------------------------------------------------- plans & packs
STRIPE_PCT, STRIPE_FIXED = 0.044, 0.30   # international card


def stripe_fee(amount):
    return amount * STRIPE_PCT + STRIPE_FIXED if amount > 0 else 0.0


PLANS = [  # code, price, monthly credits, members
    ("FREE", 0, 300, 1),
    ("STARTER", 19, 2_500, 3),
    ("PRO", 49, 7_500, 10),
    ("BUSINESS", 149, 25_000, 30),
]
PACKS = [(1_000, 10), (5_000, 45), (20_000, 160)]


def plan_rows():
    out = []
    for code, price, cr, members in PLANS:
        fee = stripe_fee(price)
        full = cr * COST_BACKING_ONE_CREDIT
        typical = full * 0.6
        margin_full = (price - fee - full) / price if price else None
        margin_typ = (price - fee - typical) / price if price else None
        out.append((code, price, cr, members, fee, full, typical, margin_full, margin_typ))
    return out


def pack_rows():
    out = []
    for cr, price in PACKS:
        fee = stripe_fee(price)
        cost = cr * COST_BACKING_ONE_CREDIT
        out.append((cr, price, price / cr, fee, cost, (price - fee - cost) / price))
    return out


# ---------------------------------------------------------------- scenarios
FIXED = {"launch": 22.0, "growth": 250.0}
FREE_USE = 0.5
PAID_USE = 0.6


def scenario(label, free, starter, pro, business, packs_revenue, fixed):
    price = {p[0]: p[1] for p in PLANS}
    credit = {p[0]: p[2] for p in PLANS}
    revenue = starter * price["STARTER"] + pro * price["PRO"] + business * price["BUSINESS"] + packs_revenue
    fees = starter * stripe_fee(price["STARTER"]) + pro * stripe_fee(price["PRO"]) + business * stripe_fee(price["BUSINESS"]) + (stripe_fee(packs_revenue) if packs_revenue else 0)
    ai = COST_BACKING_ONE_CREDIT * (
        free * credit["FREE"] * FREE_USE
        + PAID_USE * (starter * credit["STARTER"] + pro * credit["PRO"] + business * credit["BUSINESS"])
        + packs_revenue / 0.009  # credits sold in packs, all consumed
    )
    profit = revenue - fees - ai - fixed
    return label, free, starter, pro, business, revenue, fees, ai, fixed, profit, (profit / revenue if revenue else 0)


if __name__ == "__main__":
    print("## Agent turns")
    for r in turn_table():
        print(f"| {r[0]} | ${r[1]:.3f} | {r[2]} | ${r[3]:.3f} | {r[4]} |")
    for cfg in CONFIGS:
        c, k = blended(cfg)
        print(f"blended message ({cfg}): ${c:.4f} -> {k} credits")
    print("\n## Actions")
    for a in ACTIONS:
        print(f"| {a[0]} | {a[1]} | ${a[2]:.4f} | {a[3]} | {a[4]} |")
    print("\n## Plans")
    for r in plan_rows():
        mf = f"{r[7]*100:.0f}%" if r[7] is not None else "-"
        mt = f"{r[8]*100:.0f}%" if r[8] is not None else "-"
        print(f"| {r[0]} | ${r[1]} | {r[2]:,} | {r[3]} | ${r[4]:.2f} | ${r[5]:.2f} | ${r[6]:.2f} | {mf} | {mt} |")
    print("\n## Packs")
    for r in pack_rows():
        print(f"| {r[0]:,} | ${r[1]} | ${r[2]:.4f} | ${r[3]:.2f} | ${r[4]:.2f} | {r[5]*100:.0f}% |")
    print("\n## Free workspace cost")
    free_full = 300 * COST_BACKING_ONE_CREDIT
    welcome = 500 * COST_BACKING_ONE_CREDIT
    print(f"300 cr/month fully used: ${free_full:.2f}; half used: ${free_full*0.5:.2f}; 500 welcome credits: ${welcome:.2f}")
    print(f"welcome month worst case: ${(300+500)*COST_BACKING_ONE_CREDIT:.2f}")
    print("\n## Scenarios")
    for s in (
        scenario("Launch", 50, 5, 2, 0, 0, FIXED["launch"]),
        scenario("Early traction", 150, 15, 6, 1, 100, FIXED["launch"] + 60),
        scenario("Growth", 300, 40, 20, 5, 400, FIXED["growth"]),
    ):
        print(f"| {s[0]} | {s[1]} | {s[2]} | {s[3]} | {s[4]} | ${s[5]:,.0f} | ${s[6]:,.0f} | ${s[7]:,.0f} | ${s[8]:,.0f} | ${s[9]:,.0f} | {s[10]*100:.0f}% |")
    print("\n## Break-even")
    starter_gross = 19 - stripe_fee(19) - 2_500 * PAID_USE * COST_BACKING_ONE_CREDIT
    pro_gross = 49 - stripe_fee(49) - 7_500 * PAID_USE * COST_BACKING_ONE_CREDIT
    print(f"Starter gross/customer ${starter_gross:.2f}; Pro gross/customer ${pro_gross:.2f}")
    print(f"launch fixed $22 -> {math.ceil(22/starter_gross)} Starter; growth fixed $250 -> {math.ceil(250/pro_gross)} Pro or {math.ceil(250/starter_gross)} Starter")
    print(f"free workspaces one Starter carries (half use): {starter_gross/(300*FREE_USE*COST_BACKING_ONE_CREDIT):.0f}")
