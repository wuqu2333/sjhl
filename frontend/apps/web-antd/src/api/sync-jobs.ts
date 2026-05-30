import { del, post } from './request';
import type { SyncJob } from './dashboard';

export interface SyncJobSaveBody {
  id?: string;
  name?: string;
  enabled?: boolean;
  sourceType?: string;
  syncMode?: string;
  intervalMinutes?: number;
  scheduleTime?: string;
  profileId?: string;
  sourcePath?: string;
  sourceCid?: string;
  cookie?: string;
  pan115AccountId?: string;
  userAgent?: string;
  targetDir?: string;
  recursive?: boolean;
  dedupeScope?: string;
}

export const syncJobsApi = {
  save: (body: SyncJobSaveBody) => post<{ ok: true; job: SyncJob }>('/api/sync-jobs', body),
  run: (id: string) => post(`/api/sync-jobs/${id}/run`, {}),
  remove: (id: string) => del(`/api/sync-jobs/${id}`)
};
