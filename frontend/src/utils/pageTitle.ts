export const APP_NAME = 'RoleSync AI';

/**
 * Route path to page title mapping.
 */
export const ROUTE_TITLES: Record<string, string> = {
  // Public Marketing
  '/': 'RoleSync AI — The AI Operating System for Revenue Teams',
  '/home': 'RoleSync AI — The AI Operating System for Revenue Teams',
  '/features': 'Features',
  '/how-it-works': 'How It Works',
  '/integrations': 'Integrations',
  '/security': 'Security',
  '/about': 'About',
  '/contact': 'Contact',
  '/privacy': 'Privacy Policy',
  '/terms': 'Terms of Service',
  '/pricing': 'Pricing',
  '/billing/success': 'Payment',

  // Auth & Onboarding
  '/signin': 'Sign In',
  '/login': 'Sign In',
  '/register': 'Create Account',
  '/verify-email': 'Verify Email',
  '/verify-phone': 'Verify Phone',
  '/forgot-password': 'Reset Password',
  '/change-password': 'Change Password',
  '/onboarding': 'Onboarding Wizard',
  '/auth/onboarding': 'Onboarding Wizard',
  '/auth/callback': 'Authenticating',
  '/connectors/callback': 'Connecting Integration',

  // Salesman Workspace
  '/salesman': 'Knowledge Vault',
  '/salesman/knowledge-vault': 'Knowledge Vault',
  '/salesman/sales-agent': 'Sales Agent',
  '/salesman/skills': 'Agent Skills',
  '/salesman/deals': 'Deals',
  '/salesman/products': 'Product Management',
  '/salesman/external-connector': 'Data Connectors',
  '/salesman/users': 'User Management',
  '/salesman/credits': 'Credits & Usage',
  '/salesman/profile': 'Profile',
  '/salesman/settings': 'Settings',
  '/salesman/support': 'Support',
  '/salesman/ai-tasks': 'Agent Manager',
  '/salesman/workspace': 'Workspace',

  // Super Admin Console
  '/admin': 'Overview | Admin',
  '/admin/overview': 'Overview | Admin',
  '/admin/users': 'Users | Admin',
  '/admin/workspaces': 'Workspaces | Admin',
  '/admin/billing': 'Billing | Admin',
  '/admin/credits': 'Credits | Admin',
  '/admin/payments': 'Payments | Admin',
  '/admin/support': 'Support Tickets | Admin',
  '/admin/agents': 'Agent Manager | Admin',
  '/admin/models': 'AI Models | Admin',
  '/admin/prompts': 'Prompts | Admin',
  '/admin/usage': 'Usage & Costs | Admin',
  '/admin/plans': 'Plans | Admin',
  '/admin/audit': 'Audit Log | Admin',
};

/**
 * Formats a title with the RoleSync brand.
 */
export function formatTitle(title?: string): string {
  if (!title || !title.trim()) {
    return APP_NAME;
  }
  const trimmed = title.trim();
  if (trimmed.includes('RoleSync')) {
    return trimmed;
  }
  return `${trimmed} | ${APP_NAME}`;
}

/**
 * Derives a human-friendly page title from a pathname.
 */
export function deriveTitleFromPathname(pathname: string): string {
  const cleanPath = pathname.replace(/\/+$/, '') || '/';

  // Exact match
  if (ROUTE_TITLES[cleanPath]) {
    return ROUTE_TITLES[cleanPath];
  }

  // Prefix match for nested details (e.g. /salesman/deals/123 -> Deals), most specific first
  const sortedPrefixRoutes = Object.entries(ROUTE_TITLES)
    .filter(([route]) => route !== '/' && route !== '/salesman' && route !== '/admin')
    .sort((a, b) => b[0].length - a[0].length);

  for (const [route, title] of sortedPrefixRoutes) {
    if (cleanPath.startsWith(route + '/')) {
      return title;
    }
  }

  // Dynamic fallback: extract and format the last pathname segment
  const segments = cleanPath.split('/').filter(Boolean);
  if (segments.length === 0) {
    return APP_NAME;
  }

  const last = segments[segments.length - 1];
  const humanized = last
    .replace(/[-_]/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());

  const isAdmin = cleanPath.startsWith('/admin');
  return isAdmin ? `${humanized} | Admin` : humanized;
}

/**
 * Safely updates document.title in the browser.
 */
export function setDocumentTitle(title?: string): void {
  if (typeof document !== 'undefined') {
    document.title = formatTitle(title);
  }
}

// Immediately synchronize title on module initialization so title is correct
// even while React is mounting or session is verifying.
if (typeof window !== 'undefined') {
  setDocumentTitle(deriveTitleFromPathname(window.location.pathname));
}
