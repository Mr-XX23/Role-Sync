import { BRAND } from '../marketing/marketingData';

/**
 * Privacy Policy and Terms of Service, as data so both render through one page.
 * Written from what the product actually does today (see the landing page catalog);
 * have counsel review before publishing to real customers.
 */

export type LegalSlug = 'privacy' | 'terms';

export interface LegalSection {
  id: string;
  title: string;
  paragraphs?: string[];
  bullets?: string[];
  /** Optional closing paragraphs after the bullet list. */
  after?: string[];
}

export interface LegalDocument {
  slug: LegalSlug;
  path: string;
  title: string;
  summary: string;
  /** ISO date, shown as "Last updated". */
  updated: string;
  sections: LegalSection[];
}

const NAME = BRAND.name;
const CONTACT = BRAND.contactEmail;
const SUPPORT = BRAND.supportEmail;

export const PRIVACY_POLICY: LegalDocument = {
  slug: 'privacy',
  path: '/privacy',
  title: 'Privacy Policy',
  summary: `How ${NAME} collects, uses, stores and shares the information in your account and your workspace, including what the AI sales agent reads and which third parties process it.`,
  updated: '2026-09-14',
  sections: [
    {
      id: 'scope',
      title: '1. Who we are and what this covers',
      paragraphs: [
        `${NAME} is a workspace for revenue teams: an AI sales agent, a knowledge vault for your documents, a product catalog with inventory, a deals pipeline and connectors to the tools you already use. This policy explains what personal data we handle when you use the ${NAME} website and application, and the choices you have.`,
        `If you use ${NAME} through a workspace that someone else created, that workspace owner decides what content is added and who can see it. This policy describes what we do with that data on their behalf and on yours.`,
      ],
    },
    {
      id: 'collect',
      title: '2. Information we collect',
      paragraphs: ['We collect only what is needed to run the service. In practice that is:'],
      bullets: [
        'Account details: your name, email address, phone number and password. Passwords are stored as one-way hashes. If you sign in with Google, we receive your Google account name, email address and profile picture.',
        'Verification records: the emails and SMS one-time codes we send to confirm your address and phone number, and when they were used.',
        'Profile: job title, department, company, location, secondary work email, avatar image, education, skills, interests, social links, and the persona and standing instructions you give the AI agent.',
        'Workspace content you add: documents and web pages you upload to the Knowledge Vault, products, variants, stock levels and locations, deals and the contacts on them, quotes, and support requests.',
        'Conversations with the agent: your messages, files you attach, the agent’s reasoning steps, tool calls, approval decisions and answers, plus the facts the agent saves to memory about you, your customers and your deals.',
        'Connected apps: when you connect Gmail, Google Drive, Google Calendar, Slack or Notion, we store the authorisation tokens needed to access them and the items you configure the connector to sync (for example email threads, files, events, messages and pages).',
        'Preferences: theme, language, time zone and notification settings.',
        'Technical and security data: IP address, browser type, session identifiers, and a log of security events such as sign-ins, one-time codes and verification emails or messages.',
      ],
    },
    {
      id: 'use',
      title: '3. How we use it',
      bullets: [
        'To provide the service: sign you in, run your workspace, index your documents so they can be searched, and answer your questions.',
        'To operate the AI sales agent: it reads your inbox, calendar, connected apps, knowledge base, catalog, inventory and deals only in order to carry out what you ask it to do.',
        'To act on your behalf, and only after you approve: sending emails, booking meetings, posting to Slack or Notion, creating documents and quotes, updating the catalog and logging deals. Every action pauses for your approval first, and each approval and undo is recorded.',
        'To verify your identity and keep accounts safe: email and SMS verification, password resets, rate limiting and abuse detection.',
        'To support you: answering support requests and connector requests you send us.',
        'To send service messages about your account, such as verification codes and security notices. We do not send marketing email without your consent.',
      ],
      after: [
        'We do not sell your personal data, and we do not use your workspace content to train our own models.',
      ],
    },
    {
      id: 'ai',
      title: '4. AI processing and third-party providers',
      paragraphs: [
        `${NAME} relies on specialised providers to run the agent and process your content. We send them only what a given request needs, under their own privacy and security terms:`,
      ],
      bullets: [
        'Large language models: Google (Gemini) and, for some tasks or as a fallback, models served through OpenRouter, receive the messages, documents and tool results involved in a turn so the agent can reason and write.',
        'Web research: Tavily and Google Search grounding receive the search queries the agent runs on your behalf.',
        'Document parsing and OCR: LlamaParse receives PDFs, presentations, spreadsheets and images you upload so their text can be extracted.',
        'App integrations: Composio brokers the connections to Gmail, Google Drive, Google Calendar, Slack and Notion, and handles OAuth tokens and webhook deliveries.',
        'Messaging: Twilio delivers SMS verification codes; our email provider delivers verification and account emails.',
        'Images: Cloudinary hosts profile avatars.',
        'Observability: LangSmith may receive traces of agent runs, model calls and tool calls so we can diagnose failures.',
      ],
      after: [
        'When you connect a Google account, our use of information received from Google APIs follows the Google API Services User Data Policy, including the Limited Use requirements.',
      ],
    },
    {
      id: 'sharing',
      title: '5. Who can see your data inside a workspace',
      bullets: [
        'Members of a workspace can read and search its documents, catalog, deals and shared agent memory. Viewers can read but not change anything. Owners and admins manage members and can delete content.',
        'What the agent remembers about customers and deals is shared with your workspace. What it remembers about you personally is private to you.',
        'Actions the agent takes on your behalf, such as emails, are sent from your own connected accounts and are visible wherever those accounts are.',
        'We share data with the providers in section 4, with authorities when the law requires it, and with a successor if the business is transferred. Otherwise we do not share it.',
      ],
    },
    {
      id: 'retention',
      title: '6. Storage, retention and deletion',
      paragraphs: [
        'Your data is stored in databases and object storage operated for the service. Documents are kept as the original file plus extracted text, chunks and vector embeddings so they can be searched.',
      ],
      bullets: [
        'Deleting a document from the Knowledge Vault removes its text, chunks, embeddings, duplicate fingerprints and the stored original. A short record of the deletion is kept so the item is not re-imported by a connector.',
        'Disconnecting a connected app stops syncing and revokes our access to it. Items already synced remain until you delete them.',
        'You can delete individual facts from the agent’s memory at any time from the “Memory” panel or from a deal.',
        'Conversations with the agent are kept so you can resume them. Approval records and security event logs are kept for audit purposes.',
        `To delete your account, contact ${SUPPORT}. We remove or anonymise your personal data unless we must keep it to meet a legal obligation.`,
      ],
    },
    {
      id: 'cookies',
      title: '7. Cookies and local storage',
      bullets: [
        'Session cookies: after you sign in we set secure, HttpOnly cookies that hold your access and refresh tokens. They exist only to keep you signed in and are not used for tracking.',
        'Local storage: your theme choice is remembered in your browser.',
        'We do not use advertising or third-party analytics cookies.',
      ],
    },
    {
      id: 'security',
      title: '8. Security',
      bullets: [
        'Every request to the application passes through a gateway that verifies a signed token before reaching any service.',
        'Every workspace is isolated, and membership is checked on every request.',
        'Sign-up, verification and password-reset endpoints are rate limited. Security events are logged per user.',
        'Uploads and synced content are size-checked and scanned before they enter the pipeline. Junk or unreadable content is rejected or quarantined.',
        'The agent operates under limits on steps, tokens, time and budget, and cannot take a real-world action without your approval.',
      ],
      after: ['No system is perfectly secure. If you believe your account has been compromised, change your password and contact us straight away.'],
    },
    {
      id: 'rights',
      title: '9. Your rights and choices',
      bullets: [
        'Access and correction: most of your data is visible and editable in the app, including your profile, documents, deals and agent memory.',
        'Export: you can download the original of any document you uploaded. Ask us for a copy of other data we hold about you.',
        'Deletion: delete content yourself in the app, or ask us to delete your account.',
        'Connected apps: you can disconnect any app at any time from the Connectors page, and also revoke access from the provider’s own settings.',
        'Depending on where you live you may have further rights, such as objecting to certain processing or complaining to a supervisory authority. We will honour requests as the law requires.',
      ],
    },
    {
      id: 'children',
      title: '10. Children',
      paragraphs: [`${NAME} is a business tool and is not directed at children. We do not knowingly collect personal data from anyone under 16.`],
    },
    {
      id: 'changes',
      title: '11. Changes to this policy',
      paragraphs: [
        'We will update this page when our practices change and revise the date at the top. For significant changes we will also notify you in the app or by email.',
      ],
    },
    {
      id: 'contact',
      title: '12. Contact',
      paragraphs: [`Questions about privacy: ${CONTACT}. Account or data requests: ${SUPPORT}.`],
    },
  ],
};

export const TERMS_OF_SERVICE: LegalDocument = {
  slug: 'terms',
  path: '/terms',
  title: 'Terms of Service',
  summary: `The agreement between you and ${NAME} when you create an account, use a workspace, connect your tools or let the AI sales agent act for you.`,
  updated: '2026-09-14',
  sections: [
    {
      id: 'agreement',
      title: '1. Agreement',
      paragraphs: [
        `By creating an account or using ${NAME}, you agree to these terms and to our Privacy Policy. If you are using ${NAME} on behalf of a company, you confirm you are allowed to bind that company, and “you” means the company as well.`,
      ],
    },
    {
      id: 'accounts',
      title: '2. Accounts',
      bullets: [
        'You must give accurate information and keep it up to date, and verify your email address and phone number when asked.',
        'Keep your password and sign-in devices secure. You are responsible for what happens under your account until you tell us it has been compromised.',
        'You must be at least 16 and able to enter into a contract.',
        'One person per account. Invite colleagues as workspace members instead of sharing credentials.',
      ],
    },
    {
      id: 'workspaces',
      title: '3. Workspaces and roles',
      bullets: [
        'A workspace is created for you automatically. Its owner controls who joins and what role they have: admin, member or viewer.',
        'The owner and admins are responsible for the content added to a workspace and for the people they invite.',
        'Content, catalog data, deals, conversations and shared agent memory belong to the workspace and can be seen by its members according to their role.',
      ],
    },
    {
      id: 'agent',
      title: '4. The AI sales agent',
      paragraphs: [
        `${NAME} includes an AI agent that researches, drafts, prices, books and updates records on your instruction. It is a tool that you direct and supervise:`,
      ],
      bullets: [
        'Real-world actions such as sending email, booking meetings, posting to Slack or Notion, creating documents and quotes, changing the catalog or logging deals happen only after you approve them. You are responsible for what you approve, including anything you edit on the approval card.',
        'The agent can make mistakes. Its research, drafts, prices and summaries may be inaccurate or incomplete. Review them before relying on them or sending them to anyone.',
        'Undo is offered where the underlying service supports it and is provided on a best-effort basis. An email that has been delivered cannot be recalled.',
        'The agent is subject to limits on steps, tokens, time and budget per workspace and may stop a task when a limit is reached.',
      ],
    },
    {
      id: 'content',
      title: '5. Your content',
      bullets: [
        'You keep ownership of everything you add: documents, products, deals, messages and files.',
        `You give ${NAME} permission to store, process, index and transmit that content, including to the providers named in the Privacy Policy, solely to provide the service to you.`,
        'You confirm you have the right to upload the content and to connect any third-party account, and that doing so does not break the law or someone else’s rights, including the privacy rights of people whose data appears in it.',
        'We may remove content that breaks these terms or the law.',
      ],
    },
    {
      id: 'acceptable-use',
      title: '6. Acceptable use',
      paragraphs: ['You agree not to:'],
      bullets: [
        'Use the agent or connectors to send spam, unsolicited or deceptive communications, or to harass anyone.',
        'Upload malware, illegal content, or personal data you have no lawful basis to process.',
        'Probe, scan or overload the service, bypass rate limits or safety limits, or access another workspace.',
        'Reverse engineer the service, resell it, or use it to build a competing product.',
        'Use the service to make automated decisions about people that have legal or similarly significant effects on them.',
      ],
    },
    {
      id: 'third-party',
      title: '7. Connected apps and third-party services',
      bullets: [
        'Gmail, Google Drive, Google Calendar, Slack, Notion, the model providers and the other services listed in the Privacy Policy are provided by third parties under their own terms. Your use of them through RoleSync is also governed by those terms.',
        'We are not responsible for the availability, accuracy or behaviour of third-party services, or for changes they make to their APIs.',
        'You can disconnect any app at any time; doing so stops the agent from using it.',
      ],
    },
    {
      id: 'quotes',
      title: '8. Quotes, catalog and inventory',
      bullets: [
        'Quotes and documents the agent produces are drafts prepared from your catalog. Check them before you send them to a customer; they are not offers by RoleSync.',
        'Stock reservations made through the agent are yours to manage and release.',
        'You are responsible for the accuracy of prices, discounts and stock in your catalog.',
      ],
    },
    {
      id: 'fees',
      title: '9. Fees',
      paragraphs: [
        `${NAME} is currently provided without charge. If we introduce paid plans, usage credits or limits, we will explain them in advance and you will be able to choose whether to continue.`,
      ],
    },
    {
      id: 'availability',
      title: '10. Availability and changes',
      bullets: [
        'The service is under active development. We may add, change or remove features, and some features may be labelled beta or preview.',
        'We aim for high availability but do not guarantee it. Maintenance, provider outages or safety measures may interrupt the service.',
      ],
    },
    {
      id: 'termination',
      title: '11. Ending the agreement',
      bullets: [
        'You can stop using the service and ask us to delete your account at any time.',
        'We may suspend or close accounts that break these terms, create risk for other users, or have been inactive for a long time, giving notice where reasonable.',
        'Sections 4, 5, 12 and 13 continue to apply after the agreement ends.',
      ],
    },
    {
      id: 'liability',
      title: '12. Disclaimers and limitation of liability',
      paragraphs: [
        'The service, including everything the AI agent produces, is provided “as is” and “as available”, without warranties of any kind, whether express or implied, including fitness for a particular purpose and non-infringement.',
        `To the fullest extent permitted by law, ${NAME} and its team are not liable for indirect, incidental, special or consequential damages, lost profits, lost data, or losses caused by actions you approved or by third-party services. Where liability cannot be excluded, it is limited to the amount you paid us in the twelve months before the claim, or, if you paid nothing, to one hundred US dollars.`,
        'Nothing in these terms limits liability that cannot be limited by law.',
      ],
    },
    {
      id: 'general',
      title: '13. General',
      bullets: [
        'These terms are governed by the laws of the country in which RoleSync is established, without regard to conflict-of-law rules, and disputes will be brought in its courts, unless the law where you live gives you additional protection.',
        'If any part of these terms is found unenforceable, the rest still applies.',
        'We may update these terms. We will change the date at the top and, for significant changes, notify you in the app or by email. Continuing to use the service after that means you accept the updated terms.',
      ],
    },
    {
      id: 'contact',
      title: '14. Contact',
      paragraphs: [`Questions about these terms: ${CONTACT}. Support: ${SUPPORT}.`],
    },
  ],
};

export const LEGAL_DOCUMENTS: Record<LegalSlug, LegalDocument> = {
  privacy: PRIVACY_POLICY,
  terms: TERMS_OF_SERVICE,
};

export function formatUpdated(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
}
