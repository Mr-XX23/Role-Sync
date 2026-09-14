import { useCallback, useState } from 'react';
import { adminApi, adminErrorStatus, describeAdminError } from '../../api/adminApi';
import type { AdminPlan, AdminWorkspace } from '../../api/adminApi';
import { useToast } from '../../context/ToastContext';
import { ConfirmAction } from './components/AdminUi';

type Pending =
  | { kind: 'suspend'; workspace: AdminWorkspace }
  | { kind: 'reactivate'; workspace: AdminWorkspace }
  | { kind: 'plan'; workspace: AdminWorkspace; plan: AdminPlan | null; defaultPlan: AdminPlan | undefined };

/** Suspend / reactivate a workspace or change its plan, with a confirmation first. */
export function useWorkspaceActions(onDone: (workspace?: AdminWorkspace) => void) {
  const toast = useToast();
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const cancel = useCallback(() => setPending(null), []);

  const run = async (reason: string | null) => {
    if (!pending) return;
    const { workspace } = pending;
    setBusy(true);
    try {
      let updated: AdminWorkspace;
      if (pending.kind === 'plan') {
        updated = await adminApi.setWorkspacePlan(workspace.workspace_id, pending.plan?.plan_id ?? null);
        toast.success(`${workspace.name} is now on the ${updated.plan.name} plan.`, 'Plan changed');
      } else {
        const active = pending.kind === 'reactivate';
        updated = await adminApi.setWorkspaceActive(workspace.workspace_id, active, reason);
        toast.success(
          active ? `${workspace.name} is available to its members again.` : `${workspace.name} is suspended. Its members can’t open it.`,
          active ? 'Workspace reactivated' : 'Workspace suspended'
        );
      }
      setPending(null);
      onDone(updated);
    } catch (error) {
      toast.error(describeAdminError(error), 'Couldn’t update the workspace');
      setPending(null);
      if ([404, 409].includes(adminErrorStatus(error) ?? 0)) onDone();
    } finally {
      setBusy(false);
    }
  };

  let dialog = null;
  if (pending) {
    const name = <span className="font-semibold text-foreground">{pending.workspace.name}</span>;
    if (pending.kind === 'suspend') {
      dialog = (
        <ConfirmAction
          destructive
          title="Suspend this workspace?"
          message={
            <>
              Members of {name} lose access right away: its deals, products, knowledge vault and the sales agent stop working for
              them. Nothing is deleted, and you can reactivate it later.
            </>
          }
          reasonLabel="Reason"
          confirmLabel="Suspend workspace"
          busyLabel="Suspending…"
          busy={busy}
          onConfirm={(value) => void run(value)}
          onCancel={cancel}
        />
      );
    } else if (pending.kind === 'reactivate') {
      dialog = (
        <ConfirmAction
          title="Reactivate this workspace?"
          message={<>Members of {name} get their access back right away.</>}
          confirmLabel="Reactivate"
          busyLabel="Reactivating…"
          busy={busy}
          onConfirm={(value) => void run(value)}
          onCancel={cancel}
        />
      );
    } else {
      const target = pending.plan ?? pending.defaultPlan;
      dialog = (
        <ConfirmAction
          title="Change plan?"
          message={
            <>
              {name} moves from <span className="font-semibold text-foreground">{pending.workspace.plan.name}</span> to{' '}
              <span className="font-semibold text-foreground">
                {pending.plan ? pending.plan.name : `the default plan${target ? ` (${target.name})` : ''}`}
              </span>
              . New limits apply straight away; people already in the workspace keep their access even if it’s over a new member
              limit.
            </>
          }
          confirmLabel="Change plan"
          busyLabel="Saving…"
          busy={busy}
          onConfirm={(value) => void run(value)}
          onCancel={cancel}
        />
      );
    }
  }

  return {
    busy,
    dialog,
    suspend: (workspace: AdminWorkspace) => setPending({ kind: 'suspend', workspace }),
    reactivate: (workspace: AdminWorkspace) => setPending({ kind: 'reactivate', workspace }),
    changePlan: (workspace: AdminWorkspace, plan: AdminPlan | null, defaultPlan: AdminPlan | undefined) =>
      setPending({ kind: 'plan', workspace, plan, defaultPlan }),
  };
}
