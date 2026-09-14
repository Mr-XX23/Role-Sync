import { useCallback, useState } from 'react';
import { adminApi, adminErrorStatus, describeAdminError } from '../../api/adminApi';
import type { AdminUser } from '../../api/adminApi';
import { useToast } from '../../context/ToastContext';
import { UserActionDialog } from './UserActionDialog';
import type { UserAction } from './UserActionDialog';
import { userDisplayName } from './userMeta';

/** Asks for confirmation, runs one account action and says what happened (table and drawer share it). */
export function useUserActions(onDone: () => void) {
  const toast = useToast();
  const [pending, setPending] = useState<{ action: UserAction; user: AdminUser } | null>(null);
  const [busy, setBusy] = useState(false);
  const cancel = useCallback(() => setPending(null), []);

  const run = async (reason: string | null) => {
    if (!pending) return;
    const { action, user } = pending;
    const name = userDisplayName(user);
    setBusy(true);
    try {
      switch (action) {
        case 'suspend':
          await adminApi.suspendUser(user.user_id, reason);
          toast.success(`${name} is suspended and has been signed out everywhere.`, 'Account suspended');
          break;
        case 'reactivate':
          await adminApi.reactivateUser(user.user_id);
          toast.success(`${name} can sign in again.`, 'Account reactivated');
          break;
        case 'sign-out': {
          const result = await adminApi.signOutUser(user.user_id);
          toast.success(
            result.revoked_sessions > 0
              ? `Ended ${result.revoked_sessions} session${result.revoked_sessions === 1 ? '' : 's'} for ${name}.`
              : `${name} had no active sessions.`,
            'Signed out'
          );
          break;
        }
        case 'unlock':
          await adminApi.unlockUser(user.user_id);
          toast.success(`${name} can try signing in again.`, 'Account unlocked');
          break;
      }
      setPending(null);
      onDone();
    } catch (error) {
      toast.error(describeAdminError(error), 'Couldn’t update the account');
      setPending(null);
      if ([404, 409].includes(adminErrorStatus(error) ?? 0)) onDone(); // the list was out of date
    } finally {
      setBusy(false);
    }
  };

  const dialog = pending ? (
    <UserActionDialog action={pending.action} user={pending.user} busy={busy} onConfirm={(reason) => void run(reason)} onCancel={cancel} />
  ) : null;

  return { ask: (action: UserAction, user: AdminUser) => setPending({ action, user }), dialog, busy };
}
