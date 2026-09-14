import { useCallback, useEffect } from 'react';
import { useAppDispatch, useAppSelector } from '../store';
import { ensureWorkspace } from '../store/workspaceSlice';
import type { WorkspaceItem, WorkspaceStatus } from '../store/workspaceSlice';

export interface EnsuredWorkspace {
  /** Signed in: the active workspace is needed and being (or has been) loaded. */
  signedIn: boolean;
  status: WorkspaceStatus;
  error: string | null;
  workspace: WorkspaceItem | null;
  workspaces: WorkspaceItem[];
  retry: () => void;
}

/**
 * Loads the signed-in person's active workspace on pages outside the dashboard (which does this in
 * WorkspaceGate), such as /pricing, where buying credits needs to know the workspace.
 */
export function useEnsureWorkspace(): EnsuredWorkspace {
  const dispatch = useAppDispatch();
  const userId = useAppSelector((state) => (state.auth.isAuthenticated ? (state.auth.user?.userId ?? null) : null));
  const { workspaceStatus, workspaceLoadedFor, workspaceError, currentWorkspace, workspaces } = useAppSelector(
    (state) => state.workspace
  );
  const stale = workspaceStatus === 'ready' && workspaceLoadedFor !== userId;

  useEffect(() => {
    if (userId && (workspaceStatus === 'idle' || stale)) {
      void dispatch(ensureWorkspace(userId));
    }
  }, [dispatch, userId, workspaceStatus, stale]);

  const retry = useCallback(() => {
    if (userId) void dispatch(ensureWorkspace(userId));
  }, [dispatch, userId]);

  return {
    signedIn: userId !== null,
    status: stale ? 'loading' : workspaceStatus,
    error: workspaceError,
    workspace: stale ? null : currentWorkspace,
    workspaces: stale ? [] : workspaces,
    retry,
  };
}
