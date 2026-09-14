import api from './axiosInstance';
import { getActiveTenantId } from './catalogApi';

export interface ConnectResponse {
  status: string;
  source: string;
  user_id: string;
  trigger_id: string;
  redirect_url?: string | null;
  connection_state?: string;
}

export interface GmailConfig {
  max_emails_per_sync: number;
  categories: string[];
  sync_window_days: number;
  auto_sync_interval_minutes: number;
  sync_frequency?: string;
  max_attachment_size_mb: number;
  auto_sync_enabled?: boolean;
  webhook_enabled?: boolean;
}

export interface GmailConnectionDetails {
  connection_id: string;
  tenant_id: string;
  user_id: string;
  account_email: string;
  status: 'Available' | 'Configuration Required' | 'Connected' | 'Syncing' | 'Waiting for Next Auto Sync' | 'Up to Date' | 'Partial Success' | 'Failed' | 'Paused' | 'Disconnected';
  config: GmailConfig;
  backfill_state: {
    is_backfill_complete: boolean;
    oldest_synced_timestamp: string | null;
    next_page_token: string | null;
    total_eligible_discovered: number;
    total_synced_so_far: number;
  };
  lock: {
    is_locked: boolean;
    locked_by_job_id: string | null;
    locked_at: string | null;
    expires_at: string | null;
  };
  current_progress: string;
  webhook_trigger_id?: string | null;
  last_successful_sync_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface GmailStatusResponse {
  status: string;
  connection: GmailConnectionDetails;
}

export interface GmailActivityItem {
  message_id?: string;
  subject?: string;
  sender?: string;
  channel_name?: string;
  page_id?: string;
  entity_type?: string;
  status: 'SUCCESS' | 'PARTIAL_SUCCESS' | 'SKIPPED' | 'FAILED';
  attachment_summary?: string;
  error_message?: string | null;
  file_id?: string;
  filename?: string;
  name?: string;
  mime_type?: string;
  file_size?: number;
  synced_at?: string;
}


export interface GmailActivity {
  activity_id: string;
  job_id: string;
  connection_id: string;
  tenant_id: string;
  trigger_type: 'INITIAL_SYNC' | 'AUTO_SYNC' | 'MANUAL_SYNC' | 'RESYNC' | 'WEBHOOK';
  status: 'RUNNING' | 'COMPLETED' | 'PARTIAL_SUCCESS' | 'FAILED';
  started_at: string;
  completed_at?: string | null;
  metrics: {
    total_discovered: number;
    processed: number;
    succeeded: number;
    skipped: number;
    failed: number;
  };
  items: GmailActivityItem[];
}

export interface GmailActivitiesResponse {
  status: string;
  connection_id: string;
  activities: GmailActivity[];
}

/**
 * Connections belong to the active workspace (like the catalog and the vault): every call names
 * it, and data-pipeline checks the signed-in user is a member. Whose accounts are used comes from
 * the session, so no call sends a user id.
 */
const inWorkspace = () => ({ headers: { 'X-Tenant-Id': getActiveTenantId() } });

export const connectorApi = {
  connectSource: async (source: string, callbackUrl?: string): Promise<ConnectResponse> => {
    const payload: { callback_url?: string } = {};
    if (callbackUrl) {
      payload.callback_url = callbackUrl;
    }
    const response = await api.post<ConnectResponse>(`/connectors/${source}/connect`, payload, inWorkspace());
    return response.data;
  },

  // Unified Status API for All 5 Connectors
  getAllConnectorsStatus: async (): Promise<{ status: string; connections: Record<string, any> }> => {
    const response = await api.get<{ status: string; connections: Record<string, any> }>(`/connectors/status`, inWorkspace());
    return response.data;
  },

  // Gmail Specific APIs
  getGmailStatus: async (): Promise<GmailStatusResponse> => {
    const response = await api.get<GmailStatusResponse>(`/connectors/gmail/status`, inWorkspace());
    return response.data;
  },

  saveGmailConfig: async (
    maxEmailsPerSync: number,
    categories: string[],
    syncWindowDays: number = 180,
    autoSyncIntervalMinutes: number = 30,
    syncFrequency: string = '30m'
  ): Promise<any> => {
    const response = await api.post(
      `/connectors/gmail/config`,
      {
        max_emails_per_sync: maxEmailsPerSync,
        categories: categories,
        sync_window_days: syncWindowDays,
        auto_sync_interval_minutes: autoSyncIntervalMinutes,
        sync_frequency: syncFrequency,
      },
      inWorkspace()
    );
    return response.data;
  },

  updateAutoSyncSchedule: async (
    source: string,
    syncFrequency: string,
    intervalMinutes?: number,
    autoSyncEnabled?: boolean,
    webhookEnabled?: boolean
  ): Promise<any> => {
    const response = await api.post(
      `/connectors/${source.toLowerCase()}/auto-sync`,
      {
        sync_frequency: syncFrequency,
        interval_minutes: intervalMinutes,
        auto_sync_enabled: autoSyncEnabled,
        webhook_enabled: webhookEnabled,
      },
      inWorkspace()
    );
    return response.data;
  },

  triggerGmailSyncNow: async (): Promise<any> => {
    const response = await api.post(`/connectors/gmail/sync-now`, undefined, inWorkspace());
    return response.data;
  },

  triggerGmailResync: async (): Promise<any> => {
    const response = await api.post(`/connectors/gmail/resync`, undefined, inWorkspace());
    return response.data;
  },

  getGmailActivities: async (limit: number = 20): Promise<GmailActivitiesResponse> => {
    const response = await api.get<GmailActivitiesResponse>(`/connectors/gmail/activities?limit=${limit}`, inWorkspace());
    return response.data;
  },

  // Google Drive Specific APIs
  getGDriveStatus: async (): Promise<any> => {
    const response = await api.get<any>(`/connectors/gdrive/status`, inWorkspace());
    return response.data;
  },

  saveGDriveConfig: async (
    maxFilesPerSync: number,
    categories: string[],
    autoSyncIntervalMinutes: number = 30,
    syncFrequency: string = '30m'
  ): Promise<any> => {
    const response = await api.post(
      `/connectors/gdrive/config`,
      {
        max_files_per_sync: maxFilesPerSync,
        categories: categories,
        auto_sync_interval_minutes: autoSyncIntervalMinutes,
        sync_frequency: syncFrequency,
      },
      inWorkspace()
    );
    return response.data;
  },

  triggerGDriveSyncNow: async (): Promise<any> => {
    const response = await api.post(`/connectors/gdrive/sync-now`, undefined, inWorkspace());
    return response.data;
  },

  triggerGDriveResync: async (): Promise<any> => {
    const response = await api.post(`/connectors/gdrive/resync`, undefined, inWorkspace());
    return response.data;
  },

  getGDriveActivities: async (limit: number = 20): Promise<any> => {
    const response = await api.get<any>(`/connectors/gdrive/activities?limit=${limit}`, inWorkspace());
    return response.data;
  },

  // Google Calendar Specific APIs
  getCalendarStatus: async (): Promise<any> => {
    const response = await api.get<any>(`/connectors/calendar/status`, inWorkspace());
    return response.data;
  },

  saveCalendarConfig: async (
    maxEventsPerSync: number,
    categories: string[] = ['PRIMARY'],
    syncWindowDays: number = 180,
    futureWindowDays: number = 365,
    autoSyncIntervalMinutes: number = 30,
    syncFrequency: string = '30m'
  ): Promise<any> => {
    const response = await api.post(
      `/connectors/calendar/config`,
      {
        max_events_per_sync: maxEventsPerSync,
        categories: categories.length > 0 ? categories : ['PRIMARY'],
        sync_window_days: syncWindowDays,
        future_window_days: futureWindowDays,
        auto_sync_interval_minutes: autoSyncIntervalMinutes,
        sync_frequency: syncFrequency,
      },
      inWorkspace()
    );
    return response.data;
  },

  triggerCalendarSyncNow: async (): Promise<any> => {
    const response = await api.post(`/connectors/calendar/sync-now`, undefined, inWorkspace());
    return response.data;
  },

  triggerCalendarResync: async (): Promise<any> => {
    const response = await api.post(`/connectors/calendar/resync`, undefined, inWorkspace());
    return response.data;
  },

  getCalendarActivities: async (limit: number = 20): Promise<any> => {
    const response = await api.get<any>(`/connectors/calendar/activities?limit=${limit}`, inWorkspace());
    return response.data;
  },

  disconnectCalendar: async (): Promise<any> => {
    const response = await api.post(`/connectors/calendar/disconnect`, undefined, inWorkspace());
    return response.data;
  },

  getSourceActivities: async (source: string, limit: number = 20): Promise<GmailActivitiesResponse> => {
    const response = await api.get<GmailActivitiesResponse>(`/connectors/${source}/activities?limit=${limit}`, inWorkspace());
    return response.data;
  },


  disconnectGmail: async (): Promise<any> => {
    const response = await api.post(`/connectors/gmail/disconnect`, undefined, inWorkspace());
    return response.data;
  },

  disconnectSource: async (source: string): Promise<any> => {
    const response = await api.post(`/connectors/${source}/disconnect`, undefined, inWorkspace());
    return response.data;
  },

  // Slack Specific APIs
  getSlackStatus: async (): Promise<any> => {
    const response = await api.get<any>(`/connectors/slack/status`, inWorkspace());
    return response.data;
  },

  saveSlackConfig: async (
    maxMessagesPerSync: number = 15,
    categories: string[] = ['PUBLIC_CHANNELS', 'DIRECT_MESSAGES', 'GROUP_MESSAGES'],
    autoSyncIntervalMinutes: number = 30,
    syncFrequency: string = '30m'
  ): Promise<any> => {
    const response = await api.post(
      `/connectors/slack/config`,
      {
        max_messages_per_sync: maxMessagesPerSync,
        categories: categories.length > 0 ? categories : ['PUBLIC_CHANNELS', 'DIRECT_MESSAGES', 'GROUP_MESSAGES'],
        auto_sync_interval_minutes: autoSyncIntervalMinutes,
        sync_frequency: syncFrequency,
      },
      inWorkspace()
    );
    return response.data;
  },

  triggerSlackSyncNow: async (): Promise<any> => {
    const response = await api.post(`/connectors/slack/sync-now`, undefined, inWorkspace());
    return response.data;
  },

  triggerSlackResync: async (): Promise<any> => {
    const response = await api.post(`/connectors/slack/resync`, undefined, inWorkspace());
    return response.data;
  },

  getSlackActivities: async (limit: number = 20): Promise<any> => {
    const response = await api.get<any>(`/connectors/slack/activities?limit=${limit}`, inWorkspace());
    return response.data;
  },

  disconnectSlack: async (): Promise<any> => {
    const response = await api.post(`/connectors/slack/disconnect`, undefined, inWorkspace());
    return response.data;
  },

  // Notion Specific APIs
  getNotionStatus: async (): Promise<any> => {
    const response = await api.get<any>(`/connectors/notion/status`, inWorkspace());
    return response.data;
  },

  saveNotionConfig: async (
    maxItemsPerSync: number = 15,
    categories: string[] = ['PAGES', 'DATABASES'],
    autoSyncIntervalMinutes: number = 30,
    syncFrequency: string = '30m'
  ): Promise<any> => {
    const response = await api.post(
      `/connectors/notion/config`,
      {
        max_items_per_sync: maxItemsPerSync,
        categories: categories.length > 0 ? categories : ['PAGES', 'DATABASES'],
        auto_sync_interval_minutes: autoSyncIntervalMinutes,
        sync_frequency: syncFrequency,
      },
      inWorkspace()
    );
    return response.data;
  },

  triggerNotionSyncNow: async (): Promise<any> => {
    const response = await api.post(`/connectors/notion/sync-now`, undefined, inWorkspace());
    return response.data;
  },

  triggerNotionResync: async (): Promise<any> => {
    const response = await api.post(`/connectors/notion/resync`, undefined, inWorkspace());
    return response.data;
  },

  getNotionActivities: async (limit: number = 20): Promise<any> => {
    const response = await api.get<any>(`/connectors/notion/activities?limit=${limit}`, inWorkspace());
    return response.data;
  },

  disconnectNotion: async (): Promise<any> => {
    const response = await api.post(`/connectors/notion/disconnect`, undefined, inWorkspace());
    return response.data;
  },

  getSourceDataSummary: async (source: string): Promise<any> => {
    const response = await api.get(`/connectors/${source}/data-summary`, inWorkspace());
    return response.data;
  },

  purgeSourceData: async (source: string): Promise<any> => {
    const response = await api.delete(`/connectors/${source}/data`, inWorkspace());
    return response.data;
  },

  retryFailedItems: async (source: string): Promise<any> => {
    const response = await api.post(`/connectors/${source}/retry-failed`, undefined, inWorkspace());
    return response.data;
  },

  // Enterprise Custom Connector Request APIs
  requestEnterpriseSync: async (payload: EnterpriseSyncRequestPayload): Promise<{
    status: string;
    message: string;
    request: EnterpriseSyncRequestRecord;
  }> => {
    const response = await api.post<{
      status: string;
      message: string;
      request: EnterpriseSyncRequestRecord;
    }>('/connectors/enterprise-request', payload, inWorkspace());
    return response.data;
  },

  getEnterpriseSyncRequests: async (): Promise<{ status: string; requests: EnterpriseSyncRequestRecord[] }> => {
    const response = await api.get<{ status: string; requests: EnterpriseSyncRequestRecord[] }>(
      `/connectors/enterprise-requests`,
      inWorkspace()
    );
    return response.data;
  },

  cancelEnterpriseSyncRequest: async (
    requestId: string
  ): Promise<{ status: string; message: string; cancelled: boolean }> => {
    const response = await api.delete<{ status: string; message: string; cancelled: boolean }>(
      `/connectors/enterprise-requests/${requestId}`,
      inWorkspace()
    );
    return response.data;
  },
};

export interface EnterpriseSyncRequestPayload {
  database_system: string;
  requirements: string;
  contact_email?: string;
}

export interface EnterpriseSyncRequestRecord {
  request_id: string;
  user_id: string;
  tenant_id?: string;
  database_system: string;
  requirements: string;
  contact_email?: string;
  status: 'SUBMITTED' | 'UNDER_REVIEW' | 'APPROVED' | 'IN_PROGRESS' | 'ACTIVE';
  estimated_sla_hours?: number;
  created_at: string;
  updated_at?: string;
}

export default connectorApi;
