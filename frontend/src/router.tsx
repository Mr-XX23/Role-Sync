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
import { LandingPage } from './pages/marketing/LandingPage';
import { LegalPage } from './pages/legal/LegalPage';

/** Public marketing site: one scrolling page, each route scrolls to its section. */
const MARKETING_PATHS = ['/', '/home', '/features', '/how-it-works', '/integrations', '/security', '/about', '/contact'];

export const router = createBrowserRouter([
  ...MARKETING_PATHS.map((path) => ({ path, element: <LandingPage /> })),
  {
    path: '/privacy',
    element: <LegalPage slug="privacy" />,
  },
  {
    path: '/terms',
    element: <LegalPage slug="terms" />,
  },
  {
    path: '/signin',
    element: (
      <GuestRoute>
        <Signin />
      </GuestRoute>
    ),
  },
  {
    path: '/auth/callback',
    element: <OAuthCallback />,
  },
  {
    path: '/connectors/callback',
    element: <ConnectorOAuthCallback />,
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
  },
  {
    path: '/verify-email',
    element: (
      <RegistrationFlowGuard>
        <VerifyEmail />
      </RegistrationFlowGuard>
    ),
  },
  {
    path: '/verify-phone',
    element: (
      <RegistrationFlowGuard>
        <VerifyPhone />
      </RegistrationFlowGuard>
    ),
  },
  {
    path: '/forgot-password',
    element: <Passwordreset />,
  },
  {
    path: '/change-password',
    element: (
      <ProtectedRoute>
        <Changepassword />
      </ProtectedRoute>
    ),
  },
  {
    path: '/onboarding',
    element: (
      <ProtectedRoute>
        <OnboardingWizard />
      </ProtectedRoute>
    ),
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
      },
      {
        path: 'sales-agent',
        element: <SalesAgent />,
      },
      {
        path: 'skills',
        element: <Skills />,
      },
      {
        path: 'deals',
        element: <Deals />,
      },
      {
        path: 'knowledge-vault',
        element: <KnowledgeVault />,
      },
      {
        path: 'external-connector',
        element: <ExternalConnector />,
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
        path: 'users',
        element: <UserManagement />,
      },
      {
        path: 'profile',
        element: <Profile />,
      },
      {
        path: 'settings',
        element: <Settings />,
      },
      {
        path: 'support',
        element: <Support />,
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
      },
      {
        path: 'users',
        element: <AdminUsers />,
      },
      {
        path: 'workspaces',
        element: <AdminWorkspaces />,
      },
      {
        path: 'support',
        element: <AdminSupportTickets />,
      },
      {
        path: 'agents',
        element: <AdminAgents />,
      },
      {
        path: 'models',
        element: <AdminModels />,
      },
      {
        path: 'prompts',
        element: <AdminPrompts />,
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
]);
