import { del, post } from './request';
import type { TransferJob } from './dashboard';

export interface LocalUploadBody {
  profileId: string;
  localPath: string;
  remoteDir?: string;
  recursive?: boolean;
  dedupeScope?: string;
  conflictBehavior?: string;
}

export interface RemoteUrlUploadBody {
  profileId: string;
  sourceUrl?: string;
  headersText?: string;
  fileName?: string;
  remoteDir?: string;
  size?: number | string;
  sha1?: string;
  sha256?: string;
  dedupeScope?: string;
  conflictBehavior?: string;
}

export interface Pan115OpenUploadBody extends RemoteUrlUploadBody {
  accessToken?: string;
  refreshToken?: string;
  pickCode?: string;
  userAgent?: string;
}

export interface Pan115CookieUploadBody extends RemoteUrlUploadBody {
  cookie?: string;
  pickCode?: string;
  userAgent?: string;
}

export interface Pan115CloudDriveAuthBody {
  state: string;
}

export const transfersApi = {
  pan115ClouddriveAuthUrl: (body: Pan115CloudDriveAuthBody) =>
    post<{ ok: true; authorizationUrl: string }>('/api/pan115/open/clouddrive/auth-url', body),
  refreshPan115OpenToken: (body: { refreshToken: string }) =>
    post<{ ok: true; accessToken: string; refreshToken: string }>('/api/pan115/open/refresh', body),
  uploadLocal: (body: LocalUploadBody) =>
    post<{ ok: true; jobs: TransferJob[] }>('/api/uploads/local', body),
  upload115Url: (body: RemoteUrlUploadBody) =>
    post<{ ok: true; jobs: TransferJob[] }>('/api/uploads/115-url', body),
  upload115Open: (body: Pan115OpenUploadBody) =>
    post<{ ok: true; jobs: TransferJob[] }>('/api/uploads/115-open', body),
  upload115Cookie: (body: Pan115CookieUploadBody) =>
    post<{ ok: true; jobs: TransferJob[] }>('/api/uploads/115-cookie', body),
  upload115Folder: (body: Record<string, unknown>) =>
    post<{ ok: true; total: number; queued: number }>('/api/uploads/115-folder', body),
  deleteJob: (jobId: string) =>
    del<{ ok: true; deleted: boolean }>(`/api/jobs/${encodeURIComponent(jobId)}`),
  clearCompletedJobs: () =>
    del<{ ok: true; deleted: number }>('/api/jobs/completed'),
  processJobs: () =>
    post('/api/jobs/process', {}),
};
