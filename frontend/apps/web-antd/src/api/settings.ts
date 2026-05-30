import { post, request } from './request';

export interface AppSettings {
  dailyUploadLimitEnabled: boolean;
  dailyUploadLimitBytes: number;
  transferConcurrency: number;
  downloadDir: string;
  minFreeSpaceGb: number;
  workerMode: boolean;
  pan115OpenApiDelay: Pan115ApiDelaySettings;
  pan115CookieApiDelay: Pan115ApiDelaySettings;
}

export interface Pan115ApiDelaySettings {
  globalMultiplier: number;
  globalDelaySeconds: number;
  listDelaySeconds: number;
  renameDelaySeconds: number;
  deleteDelaySeconds: number;
  mutateDelaySeconds: number;
  downDelaySeconds: number;
}

export const appSettingsApi = {
  get: () => request<{ ok: true; settings: AppSettings }>('/api/settings'),
  save: (body: Partial<AppSettings>) => post<{ ok: true; settings: AppSettings }>('/api/settings', body),
};
