import { createBrowserRouter, Navigate } from 'react-router-dom';
import Signin from './pages/auth/Signin';
import OAuthCallback from './pages/auth/OAuthCallback';
import { ConnectorOAuthCallback } from './pages/salemans/externalConnector/ConnectorOAuthCallback';
import Passwordreset from './pages/auth/Passwordreset';
import Changepassword from './pages/auth/Changepassword';
import Register from './pages/auth/Register';
import VerifyPhone from './pages/auth/VerifyPhone';
import VerifyEmail from './pages/auth/VerifyEmail';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { AdminLayout } from './components/layout/AdminLayout';
import { SuperAdminRoute } from './components/guards/SuperAdminRoute';
import { AdminOverview } from './pages/admin/AdminOverview';
import { AdminUsers } from './pages/admin/AdminUsers';
import { AdminWorkspaces } from './pages/admin/AdminWorkspaces';
import { AdminAgents } from './pages/admin/AdminAgents';
import { AdminModels } from './pages/admin/AdminModels';
import { AdminPrompts } from './pages/admin/AdminPrompts';
import { AdminSupportTickets } from './pages/admin/AdminSupportTickets';
import { AdminBilling } from './pages/admin/AdminBilling';
import { AdminCredits } from './pages/admin/AdminCredits';
import { AdminPayments } from './pages/admin/AdminPayments';
import { ProtectedRoute } from './components/guards/ProtectedRoute';
import { RegistrationFlowGuard } from './components/guards/RegistrationFlowGuard';
import { GuestRoute } from './components/guards/GuestRoute';
import { OnboardingGuard } from './components/guards/OnboardingGuard';
import OnboardingWizard from './pages/auth/OnboardingWizard';
import { KnowledgeVault } from './pages/salemans/knowledgeVault/KnowledgeVault';
import { ExternalConnector } from './pages/salemans/externalConnector/ExternalConnector';
// Hidden for now: Agent Manager and Workspace pages.
// import { AiTasks } from './pages/salemans/AiTasks';
// import { Workspace } from './pages/salemans/Workspace';
import { Settings } from './pages/salemans/Settings';
import { Support } from './pages/salemans/Support';
import { Profile } from './pages/salemans/Profile';
import { ProductManagement } from './pages/salemans/productManagement/ProductManagement';
import { SalesAgent } from './pages/salemans/salesAgent/SalesAgent';
import { Skills } from './pages/salemans/skills/Skills';
import { Deals } from './pages/salemans/deals/Deals';
import { UserManagement } from './pages/salemans/userManagement/UserManagement';
import { Credits } from './pages/salemans/credits/Credits';
import { BillingSuccess } from './pages/billing/BillingSuccess';
import { LandingPage } from './pages/marketing/LandingPage';
import { PricingPage } from './pages/marketing/PricingPage';
import { LegalPage } from './pages/legal/LegalPage';
import { PageTitleManager } from './components/common/PageTitleManager';

/** Public marketing site: one scrolling page, each route scrolls to its section. */
const MARKETING_ROUTES = [
  { path: '/', title: 'RoleSync AI — The AI Operating System for Revenue Teams' },
  { path: '/home', title: 'RoleSync AI — The AI Operating System for Revenue Teams' },
  { path: '/features', title: 'Features' },
  { path: '/how-it-works', title: 'How It Works' },
  { path: '/integrations', title: 'Integrations' },
  { path: '/security', title: 'Security' },
  { path: '/about', title: 'About' },
  { path: '/contact', title: 'Contact' },
];

export const router = createBrowserRouter([
  {
    element: <PageTitleManager />,
    children: [
      ...MARKETING_ROUTES.map(({ path, title }) => ({
        path,
        element: <LandingPage />,
        handle: { title },
      })),
      {
        path: '/privacy',
        element: <LegalPage slug="privacy" />,
        handle: { title: 'Privacy Policy' },
      },
      {
        path: '/terms',
        element: <LegalPage slug="terms" />,
        handle: { title: 'Terms of Service' },
      },
      // Public pricing; signed-in visitors can buy credits for their workspace from here.
      {
        path: '/pricing',
        element: <PricingPage />,
        handle: { title: 'Pricing' },
      },
      // Where a cancelled checkout returns if billing-service still uses its older default cancel URL.
      {
        path: '/billing/cancel',
        element: <Navigate to="/pricing?checkout=cancelled" replace />,
      },
      // Stripe sends buyers back here; shown inside the workspace dashboard so the balance updates in the top bar.
      {
        path: '/billing',
        element: (
          <ProtectedRoute>
            <OnboardingGuard>
              <DashboardLayout />
            </OnboardingGuard>
          </ProtectedRoute>
        ),
        children: [
          {
            path: '',
            element: <Navigate to="/salesman/credits" replace />,
          },
          {
            path: 'success',
            element: <BillingSuccess />,
            handle: { title: 'Payment' },
          },
        ],
      },
      {
        path: '/signin',
        element: (
          <GuestRoute>
            <Signin />
          </GuestRoute>
        ),
        handle: { title: 'Sign In' },
      },
      {
        path: '/auth/callback',
        element: <OAuthCallback />,
        handle: { title: 'Authenticating' },
      },
      {
        path: '/connectors/callback',
        element: <ConnectorOAuthCallback />,
        handle: { title: 'Connecting Integration' },
      },
      {
        path: '/login',
        element: <Navigate to="/signin" replace />,
      },
      {
        path: '/register',
        element: (
          <GuestRoute>
            <Register />
          </GuestRoute>
        ),
        handle: { title: 'Create Account' },
      },
      {
        path: '/verify-email',
        element: (
          <RegistrationFlowGuard>
            <VerifyEmail />
          </RegistrationFlowGuard>
        ),
        handle: { title: 'Verify Email' },
      },
      {
        path: '/verify-phone',
        element: (
          <RegistrationFlowGuard>
            <VerifyPhone />
          </RegistrationFlowGuard>
        ),
        handle: { title: 'Verify Phone' },
      },
      {
        path: '/forgot-password',
        element: <Passwordreset />,
        handle: { title: 'Reset Password' },
      },
      {
        path: '/change-password',
        element: (
          <ProtectedRoute>
            <Changepassword />
          </ProtectedRoute>
        ),
        handle: { title: 'Change Password' },
      },
      {
        path: '/onboarding',
        element: (
          <ProtectedRoute>
            <OnboardingWizard />
          </ProtectedRoute>
        ),
        handle: { title: 'Onboarding Wizard' },
      },
      {
        path: '/auth/onboarding',
        element: <Navigate to="/onboarding" replace />,
      },
      // The Salesman Engine is the only persona, so the old picker URLs go straight to it.
      {
        path: '/workspace',
        element: <Navigate to="/salesman" replace />,
      },
      {
        path: '/select-role',
        element: <Navigate to="/salesman" replace />,
      },
      {
        path: '/salesman',
        element: (
          <ProtectedRoute>
            <OnboardingGuard>
              <DashboardLayout />
            </OnboardingGuard>
          </ProtectedRoute>
        ),
        children: [
          {
            path: '',
            element: <Navigate to="knowledge-vault" replace />,
          },
          {
            path: 'products',
            element: <ProductManagement />,
            handle: { title: 'Product Management' },
          },
          {
            path: 'sales-agent',
            element: <SalesAgent />,
            handle: { title: 'Sales Agent' },
          },
          {
            path: 'skills',
            element: <Skills />,
            handle: { title: 'Agent Skills' },
          },
          {
            path: 'deals',
            element: <Deals />,
            handle: { title: 'Deals' },
          },
          {
            path: 'knowledge-vault',
            element: <KnowledgeVault />,
            handle: { title: 'Knowledge Vault' },
          },
          {
            path: 'external-connector',
            element: <ExternalConnector />,
            handle: { title: 'Data Connectors' },
          },
          // Hidden for now: Agent Manager and Workspace routes.
          // {
          //   path: 'ai-tasks',
          //   element: <AiTasks />,
          // },
          // {
          //   path: 'workspace',
          //   element: <Workspace />,
          // },
          {
            path: 'credits',
            element: <Credits />,
            handle: { title: 'Credits & Usage' },
          },
          {
            path: 'users',
            element: <UserManagement />,
            handle: { title: 'User Management' },
          },
          {
            path: 'profile',
            element: <Profile />,
            handle: { title: 'Profile' },
          },
          {
            path: 'settings',
            element: <Settings />,
            handle: { title: 'Settings' },
          },
          {
            path: 'support',
            element: <Support />,
            handle: { title: 'Support' },
          },
        ],
      },
      // The Super Admin Console: platform super admins only (every console API checks that on the server too).
      {
        path: '/admin',
        element: (
          <ProtectedRoute>
            <SuperAdminRoute>
              <AdminLayout />
            </SuperAdminRoute>
          </ProtectedRoute>
        ),
        children: [
          {
            path: '',
            element: <Navigate to="overview" replace />,
          },
          {
            path: 'overview',
            element: <AdminOverview />,
            handle: { title: 'Overview | Admin' },
          },
          {
            path: 'users',
            element: <AdminUsers />,
            handle: { title: 'Users | Admin' },
          },
          {
            path: 'workspaces',
            element: <AdminWorkspaces />,
            handle: { title: 'Workspaces | Admin' },
          },
          {
            path: 'billing',
            element: <AdminBilling />,
            handle: { title: 'Billing | Admin' },
          },
          {
            path: 'credits',
            element: <AdminCredits />,
            handle: { title: 'Credits | Admin' },
          },
          {
            path: 'payments',
            element: <AdminPayments />,
            handle: { title: 'Payments | Admin' },
          },
          {
            path: 'support',
            element: <AdminSupportTickets />,
            handle: { title: 'Support Tickets | Admin' },
          },
          {
            path: 'agents',
            element: <AdminAgents />,
            handle: { title: 'Agent Manager | Admin' },
          },
          {
            path: 'models',
            element: <AdminModels />,
            handle: { title: 'AI Models | Admin' },
          },
          {
            path: 'prompts',
            element: <AdminPrompts />,
            handle: { title: 'Prompts | Admin' },
          },
          // Usage, Plans and Audit Log are in the nav but have no page yet.
          {
            path: '*',
            element: <Navigate to="/admin/overview" replace />,
          },
        ],
      },
      {
        path: '*',
        element: <Navigate to="/salesman" replace />,
      },
    ],
  },
]);
