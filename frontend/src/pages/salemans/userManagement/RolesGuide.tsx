import React from 'react';
import { Check, Minus } from 'lucide-react';
import type { MemberRole } from '../../../api/membersApi';
import { ROLE_META } from './memberFormat';

type Access = true | false | string; // a string: allowed with that limit

// What each role can do, as the services enforce it (workspace-service, data-pipeline, sales agent).
const CAPABILITIES: { label: string; access: Record<MemberRole, Access> }[] = [
  {
    label: 'See deals, products and the knowledge vault',
    access: { OWNER: true, ADMIN: true, MEMBER: true, VIEWER: true },
  },
  {
    label: 'Chat with the sales agent',
    access: { OWNER: true, ADMIN: true, MEMBER: true, VIEWER: 'It can’t make changes for them' },
  },
  {
    label: 'Create and edit deals',
    access: { OWNER: true, ADMIN: true, MEMBER: true, VIEWER: false },
  },
  {
    label: 'Edit products, prices and stock',
    access: { OWNER: true, ADMIN: true, MEMBER: true, VIEWER: false },
  },
  {
    label: 'Upload and reindex knowledge vault documents',
    access: { OWNER: true, ADMIN: true, MEMBER: true, VIEWER: false },
  },
  {
    label: 'Delete deals and documents',
    access: { OWNER: true, ADMIN: true, MEMBER: 'Their own', VIEWER: false },
  },
  {
    label: 'Rename the workspace and edit its description',
    access: { OWNER: true, ADMIN: true, MEMBER: false, VIEWER: false },
  },
  {
    label: 'Add people, change roles, deactivate and remove members and viewers',
    access: { OWNER: true, ADMIN: true, MEMBER: false, VIEWER: false },
  },
  {
    label: 'Make someone an admin, or change or remove an admin',
    access: { OWNER: true, ADMIN: false, MEMBER: false, VIEWER: false },
  },
];

const ROLES: MemberRole[] = ['OWNER', 'ADMIN', 'MEMBER', 'VIEWER'];

const Cell: React.FC<{ access: Access }> = ({ access }) => {
  if (access === true) {
    return <Check className="w-4 h-4 text-emerald-500 mx-auto" aria-label="Yes" />;
  }
  if (access === false) {
    return <Minus className="w-4 h-4 text-muted-foreground/50 mx-auto" aria-label="No" />;
  }
  return <span className="block text-[11px] text-muted-foreground text-center leading-tight">{access}</span>;
};

export const RolesGuide: React.FC = () => (
  <div className="space-y-4">
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
      {ROLES.map((role) => (
        <div key={role} className="bg-card border border-border/70 rounded-xl px-4 py-3 shadow-2xs">
          <span className={`inline-block text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded-md border ${ROLE_META[role].badge}`}>
            {ROLE_META[role].label}
          </span>
          <p className="text-xs text-muted-foreground mt-2 leading-relaxed">{ROLE_META[role].description}</p>
        </div>
      ))}
    </div>

    <div className="rounded-2xl border border-border/80 bg-card overflow-hidden shadow-xs">
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left">
          <thead className="bg-muted/40 text-muted-foreground uppercase text-[10px] border-b border-border/70">
            <tr>
              <th className="px-4 py-3">What they can do</th>
              {ROLES.map((role) => (
                <th key={role} className="px-4 py-3 text-center w-28">
                  {ROLE_META[role].label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {CAPABILITIES.map((capability) => (
              <tr key={capability.label}>
                <td className="px-4 py-3 text-foreground">{capability.label}</td>
                {ROLES.map((role) => (
                  <td key={role} className="px-4 py-3">
                    <Cell access={capability.access[role]} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>

    <ul className="bg-card border border-border/70 rounded-2xl px-5 py-4 space-y-1.5 text-xs text-muted-foreground list-disc list-inside shadow-2xs">
      <li>Nobody can change their own role, and the owner’s access can’t be changed or removed.</li>
      <li>Deactivated members can’t open the workspace, but their deals, notes and documents stay. Reactivate them any time.</li>
      <li>
        People you add without an account get a verified one and a temporary password by email that works for 7 days. They
        choose their own password the first time they sign in.
      </li>
      <li>Accounts created by an admin can only use the workspaces they’ve been added to.</li>
    </ul>
  </div>
);
