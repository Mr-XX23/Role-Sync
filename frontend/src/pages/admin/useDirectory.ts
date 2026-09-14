import { useMemo } from 'react';
import { adminApi } from '../../api/adminApi';
import type { AdminUser, AdminWorkspace } from '../../api/adminApi';
import { useAdminQuery } from './useAdminQuery';

export interface Directory {
  workspace: (workspaceId: string) => AdminWorkspace | undefined;
  user: (userId: string) => AdminUser | undefined;
  loading: boolean;
}

/**
 * Names for the ids the agent engine reports (it only knows workspace and user ids). Loads the
 * newest 100 workspaces and accounts; anything older falls back to a short id.
 */
export function useDirectory(): Directory {
  const query = useAdminQuery(async () => {
    const [workspaces, users] = await Promise.allSettled([
      adminApi.workspaces({ page: 0, size: 100 }),
      adminApi.users({ page: 0, size: 100 }),
    ]);
    return {
      workspaces: workspaces.status === 'fulfilled' ? workspaces.value.items : [],
      users: users.status === 'fulfilled' ? users.value.items : [],
    };
  }, 'directory');

  return useMemo(() => {
    const workspaces = new Map((query.data?.workspaces ?? []).map((item) => [item.workspace_id, item]));
    const users = new Map((query.data?.users ?? []).map((item) => [item.user_id, item]));
    return {
      workspace: (workspaceId: string) => workspaces.get(workspaceId),
      user: (userId: string) => users.get(userId),
      loading: query.loading && !query.data,
    };
  }, [query.data, query.loading]);
}
