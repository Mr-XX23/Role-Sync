import type React from 'react';
import type { LucideIcon } from 'lucide-react';
import { GmailIcon, GoogleCalendarIcon, GoogleDriveIcon, GoogleIcon, NotionIcon, SlackIcon } from './BrandIcons';
import {
  Activity,
  ArrowLeftRight,
  BadgeCheck,
  Bell,
  Blocks,
  Bot,
  Boxes,
  Brain,
  Bug,
  Building2,
  CircleDollarSign,
  Clock,
  Compass,
  Copy,
  Cpu,
  Database,
  Eye,
  FileSearch,
  FileSpreadsheet,
  FileText,
  Fingerprint,
  FolderOpen,
  Gauge,
  GitBranch,
  Globe,
  GraduationCap,
  Grid3x3,
  Handshake,
  Headset,
  History,
  KeyRound,
  Layers,
  LayoutDashboard,
  Library,
  Lightbulb,
  Link2,
  ListChecks,
  Lock,
  Mail,
  MessagesSquare,
  Orbit,
  Package,
  Palette,
  PauseCircle,
  Percent,
  Phone,
  Plug,
  Radar,
  RefreshCw,
  Route,
  ScanSearch,
  ScrollText,
  Search,
  Send,
  Server,
  Settings,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Table2,
  Tag,
  Trash2,
  TrendingUp,
  Undo2,
  Unplug,
  Upload,
  UserRound,
  Users,
  Wand2,
  Warehouse,
  Webhook,
  Zap,
} from 'lucide-react';

/* ------------------------------------------------------------------ */
/* Brand / contact                                                     */
/* ------------------------------------------------------------------ */

export const BRAND = {
  name: 'RoleSync',
  subtitle: 'Enterprise AI',
  tagline: 'The AI operating system for revenue teams.',
  /** Update to the real inbox before shipping. The contact form opens a mailto: to this address. */
  contactEmail: 'hello@rolesync.ai',
  /** Update to the real inbox before shipping. */
  supportEmail: 'support@rolesync.ai',
};

export const NAV_LINKS = [
  { label: 'Features', to: '/features' },
  { label: 'How it works', to: '/how-it-works' },
  { label: 'Integrations', to: '/integrations' },
  { label: 'About', to: '/about' },
  { label: 'Contact', to: '/contact' },
] as const;

/** Route path → section id on the landing page. */
export const ROUTE_TO_SECTION: Record<string, string> = {
  '/': 'top',
  '/home': 'top',
  '/features': 'features',
  '/how-it-works': 'how-it-works',
  '/integrations': 'integrations',
  '/security': 'security',
  '/about': 'about',
  '/contact': 'contact',
};

/* ------------------------------------------------------------------ */
/* Feature catalog                                                     */
/* ------------------------------------------------------------------ */

/** A lucide icon or one of our inline brand marks; both take a className. */
export type FeatureIcon = LucideIcon | React.FC<React.SVGProps<SVGSVGElement>>;

export interface Feature {
  icon: FeatureIcon;
  title: string;
  description: string;
  /** Short label, e.g. "Undoable" or "Human-in-the-loop". */
  badge?: string;
}

export interface FeatureArea {
  id: string;
  label: string;
  icon: FeatureIcon;
  tagline: string;
  description: string;
  features: Feature[];
}

export const FEATURE_AREAS: FeatureArea[] = [
  {
    id: 'sales-agent',
    label: 'AI Sales Agent',
    icon: Bot,
    tagline: 'An autonomous teammate that never acts without you.',
    description:
      'An orchestrator and scoped sub-agents pursue sales tasks through gated tools, stream their progress live, and pause for your approval before anything touches the real world.',
    features: [
      { icon: MessagesSquare, title: 'Chat with an autonomous agent', description: 'Ask in plain language for research, outreach, documents, quotes, deals or catalog updates.' },
      { icon: Activity, title: 'Watch it think, live', description: 'Reasoning, every step and every tool call stream into the chat in real time.' },
      { icon: PauseCircle, title: 'Approval before every action', description: 'Real-world actions pause with a preview card you approve, edit or reject.', badge: 'Human-in-the-loop' },
      { icon: ListChecks, title: 'Editable approvals', description: 'Change the wording, price or recipients on the card before you approve.' },
      { icon: Undo2, title: 'Ask-before-undo rollback', description: 'If a later step fails, one card lists exactly what it would undo, and what it cannot.' },
      { icon: GitBranch, title: 'Specialist sub-agents', description: 'Research, outreach and quote sub-agents work in parallel and report back to the orchestrator.' },
      { icon: Brain, title: 'Memory you control', description: 'It remembers facts about you, your customers and your deals. Read or delete any of them.' },
      { icon: History, title: 'Resumable conversations', description: 'Every session is saved and picks up mid-approval, even after a restart.' },
      { icon: GmailIcon, title: 'Send email', description: 'Drafts and sends Gmail on your behalf, after approval.', badge: 'Undoable' },
      { icon: GoogleCalendarIcon, title: 'Book meetings', description: 'Creates Google Calendar events. Undo cancels and notifies attendees.', badge: 'Undoable' },
      { icon: Send, title: 'Post to Slack and Notion', description: 'Sends Slack messages and creates Notion pages, both fully undoable.', badge: 'Undoable' },
      { icon: FileText, title: 'Generate documents', description: 'Produces DOCX, PPTX, XLSX, PDF or Markdown, saved to Google Drive or your Knowledge Vault.' },
      { icon: CircleDollarSign, title: 'Build priced quotes', description: 'Prices SKUs from your catalog, applies per-line discounts within limits, totals it and can reserve stock.' },
      { icon: Package, title: 'Edit the catalog by chat', description: 'Create, update or retire items and set, reserve or release stock. Never a hard delete.' },
      { icon: Handshake, title: 'Create and update deals', description: 'Logs deals, warns about duplicate open deals, and merges safely when someone else edits at the same time.' },
      { icon: Search, title: 'Search your own world', description: 'Reads your Gmail, calendar, Slack, Notion, knowledge base, catalog, inventory and deals.' },
      { icon: Globe, title: 'Web search and prospect research', description: 'Live web results condensed into a cited prospect brief.' },
      { icon: Link2, title: 'Sources on every answer', description: 'Each step shows the pages, messages or files it used or produced.' },
      { icon: ShieldAlert, title: 'Safety guardrails', description: 'Step and token limits, loop detection, per-tool circuit breakers, timeouts, approval expiry and per-workspace budgets.' },
      { icon: Lightbulb, title: 'Starter prompts', description: 'Ready-made asks for call prep, follow-ups, PDF quotes, competitive one-pagers and deal logging.' },
    ],
  },
  {
    id: 'deals',
    label: 'Deals Pipeline',
    icon: Handshake,
    tagline: 'See every opportunity, and who moved it.',
    description:
      'A visual pipeline that the agent and your team share. Quotes, contacts and memory live on the deal, and nobody overwrites anybody.',
    features: [
      { icon: LayoutDashboard, title: 'Visual deal board', description: 'Six stages: Prospecting, Qualified, Proposal, Negotiation, Won and Lost.' },
      { icon: ScrollText, title: 'Full deal record', description: 'Title, company, stage, value with currency, expected close date, next step and notes.' },
      { icon: Users, title: 'Contacts on every deal', description: 'Add multiple contacts with name, email, role and phone.' },
      { icon: FileSpreadsheet, title: 'Quotes attached to deals', description: 'Quotes the agent generates are listed on the deal they belong to.' },
      { icon: Bot, title: '"Created by agent" badge', description: 'See at a glance which deals the AI logged for you.' },
      { icon: TrendingUp, title: 'Pipeline totals and filters', description: 'Value rolled up by currency, with search and a "just mine" toggle.' },
      { icon: GitBranch, title: 'Safe concurrent editing', description: 'Two people editing the same deal never silently overwrite each other.' },
      { icon: Link2, title: 'Deep-linkable deals', description: 'Each deal has its own URL, so agent links and the back button just work.' },
      { icon: Brain, title: 'Per-deal agent memory', description: 'Open "what the agent remembers" directly from any deal.' },
    ],
  },
  {
    id: 'products',
    label: 'Products & Inventory',
    icon: Package,
    tagline: 'One catalog, every location, no oversell.',
    description:
      'Structured product data with a variant matrix, multi-location stock and an append-only ledger. The agent reads and writes it through tools, never guesses.',
    features: [
      { icon: Boxes, title: 'Products, services and retainers', description: 'Manage physical products, services and retainers with ACTIVE, DRAFT or RETIRED status.' },
      { icon: Route, title: '5-step product wizard', description: 'Concept and AI intel, option axes, variant grid, multi-location stock, publish.' },
      { icon: Grid3x3, title: 'Automatic variant matrix', description: 'Define Size, Colour or Material axes and the full SKU grid is generated for you.' },
      { icon: Wand2, title: 'Bulk price and stock apply', description: 'Set a price or an opening stock level across the whole grid in one action.' },
      { icon: Sparkles, title: 'AI findability generation', description: 'One click writes the keywords, use cases and sales intel that make a product discoverable by the agent.' },
      { icon: Percent, title: 'Discount guardrails', description: 'Set a maximum discount per item that agent quotes can never exceed.' },
      { icon: ScanSearch, title: 'Smart catalog search', description: 'BM25-ranked search over weighted product fields with optional AI synonym expansion.' },
      { icon: Tag, title: 'Product categories', description: 'A controlled, per-workspace category vocabulary.' },
      { icon: Warehouse, title: 'Multi-location inventory', description: 'Warehouses and stores with type, sellable flag and allocation priority.' },
      { icon: Table2, title: 'Inventory matrix view', description: 'A live variant by location grid of on-hand, reserved and available units.' },
      { icon: SlidersHorizontal, title: 'Set and adjust stock', description: 'Absolute set, delta adjust, and batch set across locations.' },
      { icon: ArrowLeftRight, title: 'Stock transfers', description: 'Move units between locations as a paired, auditable movement.' },
      { icon: Lock, title: 'Reserve and release', description: 'Hold stock against a quote and release it if the deal dies.' },
      { icon: History, title: 'Append-only stock ledger', description: 'Every movement is recorded with reason and reference, with full history and summaries.' },
      { icon: BadgeCheck, title: 'Deal stock check', description: 'Ask "can I actually fulfil this order?" across every hub before you promise it.' },
      { icon: Bell, title: 'Low-stock alerts', description: 'KPI cards flag items at or below threshold across all sellable hubs.' },
      { icon: Upload, title: 'CSV import with dry run', description: 'Download the template, validate every row without writing, review the error report, then commit.' },
      { icon: Trash2, title: 'Retire or delete', description: 'Soft-retire a product (the safe default) or purge it outright.' },
    ],
  },
  {
    id: 'knowledge-vault',
    label: 'Knowledge Vault',
    icon: Library,
    tagline: 'Your documents, parsed, classified and searchable by meaning.',
    description:
      'A production RAG pipeline: enterprise parsing, Gemini embeddings on pgvector, sales-aware classification and a gatekeeper that keeps junk out of your index.',
    features: [
      { icon: Upload, title: 'Drag-and-drop ingestion', description: 'PDF, DOCX, PPTX, XLSX, CSV, TSV, TXT, MD, JSON and YAML, up to 25 MB each.' },
      { icon: Globe, title: 'Ingest a web page by URL', description: 'Paste any business webpage and it is parsed and indexed like a file.' },
      { icon: FileSearch, title: 'Enterprise parsing and OCR', description: 'Complex PDFs and slides go through LlamaParse. Plain formats parse locally.' },
      { icon: Database, title: 'Vector search on pgvector', description: 'Chunks are embedded with Gemini and indexed with HNSW cosine search.' },
      { icon: SlidersHorizontal, title: 'Tunable chunking', description: 'Chunk size, overlap and similarity threshold, with Balanced, Precision and Context presets.' },
      { icon: Tag, title: 'AI sales classification', description: 'Auto-tagged as Battlecard, Pricing, Case Study, Security, Product Spec, Legal or General Resource.' },
      { icon: ScrollText, title: 'Editable sales intelligence', description: 'Override the category and add target competitor, target industry, a summary and tags.' },
      { icon: RefreshCw, title: 'Re-classify on demand', description: 'Ask the AI to re-read and re-tag a document.' },
      { icon: Activity, title: 'Live pipeline table', description: 'Watch each document move from Parsing to Indexed, with adaptive auto-refresh.' },
      { icon: Eye, title: 'Vector inspector', description: 'Open any document and read its actual chunks, embedding model and full parsed text.' },
      { icon: FolderOpen, title: 'Download the original', description: 'The raw uploaded file is kept and downloadable.' },
      { icon: Copy, title: 'Duplicate cleanup', description: 'Scan the vault for duplicate documents, preview the groups, then remove them.' },
      { icon: Fingerprint, title: 'Duplicate upload detection', description: 'Re-uploading an identical file is recognised and skipped instead of re-indexed.' },
      { icon: Zap, title: 'Re-index a document', description: 'Force a fresh parse and embed of any document.' },
      { icon: Trash2, title: 'Full purge on delete', description: 'Removes text, chunks, vectors, fingerprints, the stored original and the registry row, with a tombstone.' },
      { icon: ShieldAlert, title: 'Content gatekeeper', description: 'Junk, corrupted, encrypted or off-topic uploads are rejected or quarantined before they pollute your index.' },
      { icon: ListChecks, title: 'Quarantine review', description: 'See held documents and release them into the index yourself.' },
      { icon: Bug, title: 'Malware and type scanning', description: 'Uploads and connector payloads run the same size and malware policy.' },
      { icon: KeyRound, title: 'Permission-aware retrieval', description: 'Members read and search. Viewers cannot change anything. Only the uploader or an admin can delete.' },
      { icon: Gauge, title: 'Vault KPI dashboard', description: 'Document count, indexed count, total chunks, stored bytes and connected sources at a glance.' },
      { icon: Server, title: 'Ingestion queue health', description: 'Queue stats, dead-letter listing and replay for failed ingestion jobs.' },
      { icon: Radar, title: 'Reconciliation sweeper', description: 'Re-checks connected sources so upstream deletions and permission changes are reflected in your index.' },
    ],
  },
  {
    id: 'connectors',
    label: 'Data Connectors',
    icon: Plug,
    tagline: 'Bring the tools your team already lives in.',
    description:
      'OAuth in a popup, configure what to pull, and let scheduled or webhook sync keep your knowledge fresh without lifting a finger.',
    features: [
      { icon: GmailIcon, title: 'Gmail', description: 'Sync email threads, customer correspondence and attachments into workspace knowledge.' },
      { icon: GoogleDriveIcon, title: 'Google Drive', description: 'Index spreadsheets, contract PDFs and slide decks straight from Drive.' },
      { icon: GoogleCalendarIcon, title: 'Google Calendar', description: 'Pull client demos, sales reviews and meeting agendas into context.' },
      { icon: SlackIcon, title: 'Slack', description: 'Capture lead threads, sales alerts and channel discussions, including DMs.' },
      { icon: NotionIcon, title: 'Notion', description: 'Map internal wikis, database boards and process pages into the index.' },
      { icon: KeyRound, title: 'One-click OAuth connect', description: 'Authorise each app in a popup. No keys to copy.' },
      { icon: Settings, title: 'Per-connector sync configuration', description: 'Choose how many items to pull and which categories, channels or calendars to include.' },
      { icon: Clock, title: 'Scheduled auto-sync', description: 'Keep sources fresh every 2 minutes, 30 minutes, hourly, 6-hourly or daily.' },
      { icon: Webhook, title: 'Webhook push sync', description: 'Real-time updates via provider webhooks instead of polling.' },
      { icon: RefreshCw, title: 'Sync now or full re-sync', description: 'Trigger an immediate incremental sync or a complete re-pull at any time.' },
      { icon: ScrollText, title: 'Sync activity log', description: 'Every sync run with items captured, succeeded and failed, per source.' },
      { icon: Zap, title: 'Retry failed items', description: 'Re-queue the items that failed in a previous sync.' },
      { icon: Unplug, title: 'Disconnect any source', description: 'Revoke a connection in one click.' },
      { icon: Activity, title: 'Connection status dashboard', description: 'Live status for every connector, searchable, with a KPI card on the vault page.' },
      { icon: Building2, title: 'Request an enterprise connector', description: 'Ask for a custom database or system integration and track your request in the UI.' },
      { icon: Lock, title: 'Rate limiting and distributed locking', description: 'Syncs are throttled and never run twice at once across instances.' },
    ],
  },
  {
    id: 'security',
    label: 'Accounts & Security',
    icon: ShieldCheck,
    tagline: 'Enterprise-grade sign-in from day one.',
    description:
      'Verified identities, hardened sessions and a single signed gateway in front of every service.',
    features: [
      { icon: KeyRound, title: 'Email and password sign-up', description: 'Strength-enforced passwords with a live strength meter.' },
      { icon: GoogleIcon, title: 'Sign in with Google', description: 'One-click Google OAuth2 login as an alternative to a password.' },
      { icon: Mail, title: 'Email verification', description: 'Confirm your address from a verification email before your workspace unlocks.' },
      { icon: Phone, title: 'Phone and SMS OTP verification', description: 'Verify a phone number with a one-time code sent by SMS.' },
      { icon: Activity, title: 'Live verification status', description: 'The sign-up screen updates itself the moment you click the link in your inbox.' },
      { icon: RefreshCw, title: 'Password reset by link or OTP', description: 'Reset a forgotten password via an emailed link or a one-time code.' },
      { icon: Lock, title: 'Secure sessions', description: 'HttpOnly cookie sessions that refresh silently, plus logout and admin force-logout.' },
      { icon: ShieldAlert, title: 'Abuse protection', description: 'Registration, OTP and reset endpoints are rate-limited to stop spam and brute force.' },
      { icon: Server, title: 'Signed-token API gateway', description: 'Every API call is verified at a single gateway with RS256 and JWKS before it reaches a service.' },
      { icon: ScrollText, title: 'Security audit trail', description: 'Login, OTP, email and SMS events are logged per user.' },
    ],
  },
  {
    id: 'workspaces',
    label: 'Workspaces & Team',
    icon: Users,
    tagline: 'Set up in a minute, scale to the whole team.',
    description:
      'Everything is scoped to a workspace, membership is verified on every call, and preferences follow each person across devices.',
    features: [
      { icon: Route, title: '3-step onboarding wizard', description: 'Tell us who you are, pick a theme and language, and you are set up in under a minute.' },
      { icon: Compass, title: 'Role and persona picker', description: 'Choose the workspace persona you want to work in. Salesman Engine ships today.' },
      { icon: Zap, title: 'Instant personal workspace', description: 'Everyone gets a workspace automatically on first use. No setup step.' },
      { icon: Layers, title: 'Multiple workspaces', description: 'Create and switch between workspaces. Every document, product and deal is scoped to one.' },
      { icon: Users, title: 'Team members with roles', description: 'Invite people as ADMIN, MEMBER or VIEWER. Only the OWNER can grant ADMIN.' },
      { icon: Eye, title: 'Read-only viewer mode', description: 'Viewers see everything but cannot change catalog, stock, deals or shared agent memory.' },
      { icon: Settings, title: 'Workspace preferences', description: 'Per-user theme, language, timezone and notification toggles that follow you across devices.' },
      { icon: Palette, title: 'Light, dark and system theme', description: 'A theme toggle in the header, remembered on the server.' },
    ],
  },
  {
    id: 'profile',
    label: 'Profile & AI Persona',
    icon: UserRound,
    tagline: 'Teach the agent to sound like you.',
    description:
      'Your profile is more than a card. The agent reads your persona, tone and standing instructions on every turn.',
    features: [
      { icon: UserRound, title: 'Rich rep profile', description: 'Name, alias, job title, department, company, location, phone and a secondary work email.' },
      { icon: Upload, title: 'Avatar upload', description: 'Drop in a photo or paste an image link.' },
      { icon: GraduationCap, title: 'Education and credentials', description: 'Record degrees and qualifications on your profile.' },
      { icon: Wand2, title: 'AI persona and custom instructions', description: 'Tell the AI how to write as you: tone, persona and standing instructions reused in every turn.' },
      { icon: Tag, title: 'Skills, tools and interests', description: 'Tag your expertise so the agent knows what you actually sell.' },
      { icon: Layers, title: 'Workspace settings tab', description: 'Rename your workspace and see every workspace you belong to.' },
      { icon: Link2, title: 'Social and professional links', description: 'LinkedIn, GitHub, X, Facebook, Instagram and a personal site.' },
    ],
  },
  {
    id: 'settings',
    label: 'Settings & Support',
    icon: Settings,
    tagline: 'Tune the engine, get help fast.',
    description: 'Calibrate retrieval, manage credentials and reach support without leaving the app.',
    features: [
      { icon: SlidersHorizontal, title: 'RAG calibration', description: 'Tune chunk size, overlap and similarity filter, or pick a preset, with one-click reset to defaults.' },
      { icon: KeyRound, title: 'API credentials', description: 'Store your embedding token and CRM endpoint.' },
      { icon: Activity, title: 'Cluster diagnostics', description: 'A health view of the services behind your workspace.' },
      { icon: Headset, title: 'Support desk', description: 'File a support ticket with a subject and description from inside the app.' },
      { icon: Radar, title: 'Diagnostic node stream', description: 'A live system-diagnostics panel next to the ticket form.' },
    ],
  },
  {
    id: 'platform',
    label: 'Platform Foundations',
    icon: Server,
    tagline: 'The engineering underneath the experience.',
    description: 'Built as isolated microservices with failover, tracing and checkpointed runs so a bad minute never becomes a bad day.',
    features: [
      { icon: Lock, title: 'Workspace-isolated by design', description: 'Every document, product, deal, session and memory is scoped to a workspace and membership is verified on every call.' },
      { icon: Blocks, title: 'Microservice architecture', description: 'Spring Cloud gateway, config and discovery in front of auth, workspace, data-pipeline and agent services.' },
      { icon: ScrollText, title: 'Full audit trail on AI actions', description: 'Every tool call, approval decision and undo is recorded under the agent that made it.' },
      { icon: Orbit, title: 'Model failover', description: 'Gemini primary with OpenRouter failover, so a provider outage does not stop a turn.' },
      { icon: Radar, title: 'Observability and tracing', description: 'Every session run, LLM call and tool call can be traced end to end.' },
      { icon: Cpu, title: 'Crash-resilient runs', description: 'A run whose process dies resumes from its checkpoint. An unknown-outcome write is never silently retried.' },
    ],
  },
];

export const TOTAL_FEATURES = FEATURE_AREAS.reduce((n, a) => n + a.features.length, 0);

/* ------------------------------------------------------------------ */
/* Supporting content                                                  */
/* ------------------------------------------------------------------ */

export const STATS = [
  { value: TOTAL_FEATURES, suffix: '+', label: 'Shipped capabilities' },
  { value: 5, suffix: '', label: 'Native connectors' },
  { value: 11, suffix: '', label: 'Document formats' },
  { value: 100, suffix: '%', label: 'Actions human-approved' },
];

export const HOW_IT_WORKS = [
  {
    icon: Plug,
    title: 'Connect',
    description: 'Link Gmail, Drive, Calendar, Slack and Notion in a popup. Drop in your battlecards, price lists and specs.',
  },
  {
    icon: Library,
    title: 'Ingest',
    description: 'Documents are parsed, classified, embedded on pgvector and gated for quality. Your catalog stays structured.',
  },
  {
    icon: Bot,
    title: 'Ask',
    description: 'Tell the agent what you need. It researches, drafts, prices and books while you watch every step stream in.',
  },
  {
    icon: BadgeCheck,
    title: 'Approve',
    description: 'Nothing leaves the building until you say so. Approve, edit or reject each action, and undo if you change your mind.',
  },
];

export const TRUST_PILLARS = [
  {
    icon: PauseCircle,
    title: 'Human in the loop',
    description: 'Every email, meeting, post, quote and catalog write pauses for your decision. Guardrails cap steps, tokens and budgets per workspace.',
  },
  {
    icon: Lock,
    title: 'Workspace isolation',
    description: 'Tenancy is enforced at the data layer and re-checked on every call. Viewers read, members act, owners govern.',
  },
  {
    icon: ScrollText,
    title: 'Complete audit trail',
    description: 'Tool calls, approvals, undos and security events are recorded. Deletion purges vectors, files and fingerprints with a tombstone.',
  },
  {
    icon: ShieldCheck,
    title: 'Hardened edge',
    description: 'RS256 tokens verified at one gateway, HttpOnly refresh sessions, rate-limited auth endpoints and malware-scanned uploads.',
  },
];

export const VALUES = [
  {
    icon: Eye,
    title: 'Transparent by default',
    description: 'You see the reasoning, the tools and the sources. An AI you cannot inspect is an AI you cannot trust.',
  },
  {
    icon: PauseCircle,
    title: 'Consent before action',
    description: 'Autonomy is only useful when you stay in control. Approval is a feature, not a speed bump.',
  },
  {
    icon: Database,
    title: 'Structured where it matters',
    description: 'Catalog and inventory live in typed tables the agent queries through tools. Embeddings are for documents, not prices.',
  },
  {
    icon: Blocks,
    title: 'Built to be operated',
    description: 'Isolated services, tracing, failover, checkpoints and queue health are part of the product, not an afterthought.',
  },
];

export const TECH_STACK = [
  'LangGraph',
  'Gemini',
  'OpenRouter',
  'pgvector',
  'PostgreSQL',
  'Redis',
  'MinIO',
  'LlamaParse',
  'Tavily',
  'LangSmith',
  'Composio',
  'Spring Cloud',
  'React 19',
  'Cloudinary',
  'Twilio',
];

export const INTEGRATIONS = [
  { name: 'Gmail', kind: 'Email' },
  { name: 'Google Drive', kind: 'Files' },
  { name: 'Google Calendar', kind: 'Meetings' },
  { name: 'Slack', kind: 'Chat' },
  { name: 'Notion', kind: 'Wiki' },
  { name: 'Google Sign-In', kind: 'Identity' },
];

export const ROADMAP = [
  { icon: Orbit, title: 'Long-running goals', description: 'Autonomy that pursues multi-day objectives with escalation policies.' },
  { icon: CircleDollarSign, title: 'Billing and credits', description: 'Usage credits with Stripe, eSewa and Khalti checkout.' },
  { icon: GraduationCap, title: 'More personas', description: 'AI Tutor Console and Student Desk join the Salesman Engine.' },
  { icon: Activity, title: 'Audio and video transcription', description: 'Call recordings and demos become searchable knowledge.' },
];
