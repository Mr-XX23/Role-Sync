import React from 'react';
import type { AdminUser } from '../../api/adminApi';
import { ConfirmAction } from './components/AdminUi';
import { userDisplayName } from './userMeta';

export type UserAction = 'suspend' | 'reactivate' | 'sign-out' | 'unlock';

export const UserActionDialog: React.FC<{
  action: UserAction;
  user: AdminUser;
  busy: boolean;
  onConfirm: (reason: string | null) => void;
  onCancel: () => void;
}> = ({ action, user, busy, onConfirm, onCancel }) => {
  const name = <span className="font-semibold text-foreground">{userDisplayName(user)}</span>;
  switch (action) {
    case 'suspend':
      return (
        <ConfirmAction
          destructive
          title="Suspend this account?"
          message={
            <>
              {name} ({user.email}) will be signed out of every device and won’t be able to sign in until you reactivate them.
              Their workspaces and data stay as they are.
            </>
          }
          reasonLabel="Reason"
          confirmLabel="Suspend account"
          busyLabel="Suspending…"
          busy={busy}
          onConfirm={onConfirm}
          onCancel={onCancel}
        />
      );
    case 'reactivate':
      return (
        <ConfirmAction
          title="Reactivate this account?"
          message={<>{name} will be able to sign in again right away.</>}
          confirmLabel="Reactivate"
          busyLabel="Reactivating…"
          busy={busy}
          onConfirm={onConfirm}
          onCancel={onCancel}
        />
      );
    case 'sign-out':
      return (
        <ConfirmAction
          title="Sign out everywhere?"
          message={
            <>
              Ends every session {name} has. They can sign in again straight away, so use this after a lost device or a password
              concern. Pages already open elsewhere stop working within the hour.
            </>
          }
          confirmLabel="Sign out everywhere"
          busyLabel="Signing out…"
          busy={busy}
          onConfirm={onConfirm}
          onCancel={onCancel}
        />
      );
    case 'unlock':
      return (
        <ConfirmAction
          title="Unlock sign-in?"
          message={<>Clears the failed sign-in count for {name}, so they can try again now instead of waiting.</>}
          confirmLabel="Unlock"
          busyLabel="Unlocking…"
          busy={busy}
          onConfirm={onConfirm}
          onCancel={onCancel}
        />
      );
  }
};
