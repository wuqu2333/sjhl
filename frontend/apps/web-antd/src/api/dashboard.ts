import { request } from './request';

export interface AppInfo {
  name: string;
  dataDir: string;
  graphBaseUrl: string;
  authBaseUrl: string;
}

export interface Profile {
  id: string;
  name: string;
  authMode: string;
  region: string;
  tenantId: string;
  clientId: string;
  driveId: string;
  siteId: string;
  libraryName: string;
  rootPath: string;
  capacityEnabled: boolean;
  capacityPoolId: string;
  quotaTotal: number;
  quotaUsed: number;
  quotaRemaining: number;
  quotaState: string;
  createdAt: string;
  updatedAt: string;
}

export interface CapacityPool {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
}

export interface TenantConnection {
  id: string;
  name: string;
  authMode: string;
  region: string;
  tenantId: string;
  importDocumentsOnly: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface SyncJob {
  id: string;
  name: string;
  enabled: boolean;
  sourceType: string;
  syncMode: string;
  intervalMinutes: number;
  scheduleTime: string;
  profileId: string;
  sourcePath: string;
  sourceCid: string;
  targetDir: string;
  recursive: boolean;
  lastStatus: string;
  lastRunAt: string;
  nextRunAt: string;
  lastError: string;
  lastSummary: Record<string, unknown>;
  hasCookie: boolean;
  logs?: Array<{ at: string; message: string }>;
  createdAt: string;
  updatedAt: string;
}

export interface TransferJob {
  id: string;
  type: string;
  status: string;
  profile_id: string;
  profile_name: string;
  file_name: string;
  remote_path: string;
  remote_dir: string;
  size: number;
  uploaded?: number;
  total?: number;
  percent: number;
  last_error: string;
  progress: {
    uploaded: number;
    downloaded: number;
    total: number;
    percent: number;
  };
  speed?: number;
  download_speed?: number;
  staged?: boolean;
  logs: Array<{ at: string; message: string }>;
  created_at: string;
  updated_at: string;
}

export interface DedupeState {
  count: number;
  latest: Array<Record<string, unknown>>;
}

export interface DashboardStats {
  todayUploaded: {
    fileCount: number;
    totalSize: number;
    startAt: string;
    endAt: string;
    timezone: string;
  };
}

export interface JobStats {
  statusCounts: Record<string, number>;
}

export interface AppSettings {
  dailyUploadLimitEnabled: boolean;
  dailyUploadLimitBytes: number;
  transferConcurrency: number;
}

export interface ApiState {
  app: AppInfo;
  profiles: Profile[];
  capacityPools: CapacityPool[];
  tenantConnections: TenantConnection[];
  syncJobs: SyncJob[];
  catalogScan: Record<string, unknown>;
  jobs: TransferJob[];
  jobStats?: JobStats;
  dedupe: DedupeState;
  settings: AppSettings;
  stats: DashboardStats;
}

export const dashboardApi = {
  state: (options: { jobsLimit?: number } = {}) => {
    const params = new URLSearchParams();
    if (options.jobsLimit) params.set('jobsLimit', String(options.jobsLimit));
    const query = params.toString();
    return request<{ ok: true } & ApiState>(`/api/state${query ? `?${query}` : ''}`);
  }
};
