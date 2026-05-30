<template>
  <div class="space-y-4">
    <!-- 统计卡片 -->
    <div class="grid grid-cols-4 gap-2">
      <a-card size="small" class="metric-card" :body-style="metricBodyStyle">
        <div class="metric-title">SP 容量池</div>
        <div class="metric-value">{{ enabledProfileCount }}<span>个</span></div>
      </a-card>
      <a-card size="small" class="metric-card" :body-style="metricBodyStyle">
        <div class="metric-title">传输任务</div>
        <div class="metric-value" :class="{ 'metric-primary': activeJobCount > 0 }">{{ activeJobCount }}<span>个</span></div>
        <div class="metric-sub metric-sub-status">
          <span>{{ runningJobCount }} 上传</span>
          <span>{{ queuedOnlyJobCount }} 等待</span>
          <span>{{ retryJobCount }} 重试</span>
        </div>
      </a-card>
      <a-card size="small" class="metric-card" :body-style="metricBodyStyle">
        <div class="metric-title">去重指纹</div>
        <div class="metric-value">{{ store.state?.dedupe.count || 0 }}<span>条</span></div>
      </a-card>
      <a-card size="small" class="metric-card" :body-style="metricBodyStyle">
        <div class="metric-title">已用容量</div>
        <div class="metric-value">{{ totalUsed > 0 ? formatBytes(totalUsed).value : '-' }}<span>{{ totalUsed > 0 ? formatBytes(totalUsed).unit : '' }}</span></div>
      </a-card>
    </div>

    <a-card size="small" :body-style="{ padding: '10px 12px' }">
      <div class="flex items-center justify-between gap-3">
        <div class="text-sm text-text-muted">今日上传总量</div>
        <div class="text-lg font-semibold whitespace-nowrap">{{ todayUploadedSizeText }}</div>
        <div class="text-xs text-text-muted whitespace-nowrap">{{ todayUploadedFileCount }} 个文件</div>
      </div>
    </a-card>

    <!-- 快捷操作 -->
    <div class="flex flex-wrap gap-2">
      <a-button type="primary" @click="router.push('/transfers')">上传文件</a-button>
      <a-button @click="router.push('/files')">浏览文件</a-button>
      <a-button @click="router.push('/settings')">管理 SP</a-button>
      <a-button @click="store.loadState()" :loading="refreshing">刷新状态</a-button>
    </div>

    <!-- 传输队列 -->
    <a-card title="传输队列" size="small">
      <template #extra>
        <a-space wrap :size="6">
          <a-tag v-if="totalUploadSpeed > 0" color="blue">总速率 {{ formatSpeed(totalUploadSpeed) }}</a-tag>
          <a-tag color="blue">{{ runningJobCount }} 上传</a-tag>
          <a-tag>{{ queuedOnlyJobCount }} 等待</a-tag>
          <a-tag color="orange">{{ retryJobCount }} 重试</a-tag>
          <a-button size="small" type="primary" @click="triggerProcess">开始处理</a-button>
          <a-button v-if="completedJobCount > 0" size="small" @click="clearCompletedJobs">清理已完成</a-button>
          <a-button size="small" @click="store.loadState()">刷新</a-button>
        </a-space>
      </template>
      <a-empty v-if="!queueJobs.length" description="暂无传输任务" :image-style="{ height: '48px' }" />
      <div v-else class="space-y-2">
        <div v-for="job in queueJobs" :key="job.id" class="p-2 rounded-lg border border-border">
          <div class="flex items-center justify-between gap-2 mb-1">
            <div class="min-w-0 flex-1">
              <div class="text-sm truncate" :title="job.file_name || job.remote_path">{{ job.file_name || job.remote_path }}</div>
              <div class="text-xs text-text-muted">{{ job.profile_name }} · {{ job.type }} · {{ jobStageLabel(job) }}</div>
            </div>
            <a-space>
              <a-tag :color="jobStageColor(job)">{{ jobStageLabel(job) }}</a-tag>
              <a-button size="small" danger :loading="deletingJobIds.has(job.id)" @click="deleteJob(job.id)">删除</a-button>
            </a-space>
          </div>
          <div v-if="(job.total || 0) > 0" class="flex items-center gap-2">
            <a-progress
              :percent="Math.round((job.uploaded || 0) / (job.total || 1) * 100)"
              :status="job.status === 'failed' ? 'exception' : job.status === 'done' ? 'success' : 'active'"
              size="small"
              class="flex-1"
            />
            <span v-if="job.speed && job.status === 'running'" class="text-xs text-blue-500 shrink-0">↑ {{ formatSpeed(job.speed) }}</span>
          </div>
          <div v-if="job.last_error" class="text-xs text-red-500 truncate mt-1">{{ job.last_error }}</div>
          <div v-else-if="job.status === 'retry'" class="text-xs text-orange-500 truncate mt-1">等待自动重试</div>
        </div>
      </div>
    </a-card>

    <!-- 容量池概览 -->
    <a-card title="容量池概览" size="small">
      <template #extra>
        <a-button size="small" :loading="refreshingCapacity" @click="refreshAllCapacity">刷新容量</a-button>
      </template>
      <a-empty v-if="!store.state?.profiles.length" description="暂无 SP" :image-style="{ height: '48px' }" />
      <div v-else class="space-y-2">
        <div v-for="profile in capacityProfiles.slice(0, 8)" :key="profile.id" class="rounded-lg border border-border p-2.5">
          <div class="flex items-center justify-between gap-2 mb-1.5">
            <span class="text-sm font-medium truncate min-w-0">{{ profile.name }}</span>
            <a-tag :color="profile.capacityEnabled !== false ? 'blue' : 'default'" class="shrink-0">
              {{ profile.capacityEnabled !== false ? '启用' : '未启用' }}
            </a-tag>
          </div>
          <a-progress
            :percent="quotaPercent(profile)"
            :status="profile.quotaState === 'full' ? 'exception' : 'normal'"
            :show-info="false"
            size="small"
          />
          <div class="flex items-center justify-between gap-2 text-xs text-text-muted mt-1">
            <span>已用 {{ fmt(profileUsed(profile)) }}</span>
            <span>剩余 {{ fmt(profileRemaining(profile)) }}</span>
            <span>总量 {{ fmt(profile.quotaTotal) }}</span>
          </div>
        </div>
      </div>
    </a-card>

    <!-- 同步作业状态 -->
    <a-card title="同步作业" size="small">
      <a-empty v-if="!store.state?.syncJobs.length" description="暂无同步作业" :image-style="{ height: '48px' }" />
      <div v-else class="space-y-2">
        <div
          v-for="job in store.state?.syncJobs"
          :key="job.id"
          class="flex items-center justify-between gap-2 p-2 rounded-lg border border-border"
        >
          <div class="min-w-0">
            <div class="text-sm truncate">{{ job.name }}</div>
            <div class="text-xs text-text-muted">
              {{ job.sourceType === 'local' ? '本地' : '115' }} → {{ job.targetDir || '/' }}
              · {{ job.lastStatus || 'idle' }}
            </div>
          </div>
          <a-tag :color="job.lastStatus === 'running' ? 'blue' : job.lastStatus === 'failed' ? 'red' : 'default'">
            {{ job.lastStatus || '空闲' }}
          </a-tag>
        </div>
      </div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAppStore } from '../../stores/useAppStore';
import { capacityApi } from '../../api/capacity';
import { transfersApi } from '../../api/transfers';

const store = useAppStore();
const router = useRouter();
const refreshing = ref(false);
const refreshingCapacity = ref(false);
const deletingJobIds = ref(new Set<string>());
const metricBodyStyle = { padding: '10px 6px' };
const queueStatuses = new Set(['queued', 'retry', 'running', 'failed']);
const completedStatuses = new Set(['done', 'skipped', 'cancelled']);

const runningJobs = computed(() => (store.state?.jobs || []).filter((j) => j.status === 'running'));
const queuedJobs = computed(() => (store.state?.jobs || []).filter((j) => ['queued', 'retry'].includes(j.status)));
const jobStatusCounts = computed<Record<string, number>>(() => {
  const counts = store.state?.jobStats?.statusCounts;
  if (counts) return counts;
  return (store.state?.jobs || []).reduce((acc, job) => {
    acc[job.status] = (acc[job.status] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);
});
const runningJobCount = computed(() => Number(jobStatusCounts.value.running || 0));
const queuedOnlyJobCount = computed(() => Number(jobStatusCounts.value.queued || 0));
const retryJobCount = computed(() => Number(jobStatusCounts.value.retry || 0));
const queuedJobCount = computed(() => queuedOnlyJobCount.value + retryJobCount.value);
const activeJobCount = computed(() => runningJobCount.value + queuedJobCount.value);
const totalUploadSpeed = computed(() =>
  runningJobs.value.reduce((sum, job) => sum + Number(job.speed || 0), 0)
);
const enabledProfileCount = computed(() =>
  (store.state?.profiles || []).filter((profile) => profile.capacityEnabled !== false).length
);
const capacityProfiles = computed(() =>
  [...(store.state?.profiles || [])].sort((a, b) => {
    const enabledDelta = Number(b.capacityEnabled !== false) - Number(a.capacityEnabled !== false);
    if (enabledDelta !== 0) return enabledDelta;
    return quotaPercent(b) - quotaPercent(a);
  })
);

const totalUsed = computed(() =>
  (store.state?.profiles || [])
    .filter((profile) => profile.capacityEnabled !== false)
    .reduce((sum, p) => sum + profileUsed(p), 0)
);
const todayUploadedSize = computed(() => store.state?.stats?.todayUploaded?.totalSize || 0);
const todayUploadedFileCount = computed(() => store.state?.stats?.todayUploaded?.fileCount || 0);
const todayUploadedSizeText = computed(() => fmt(todayUploadedSize.value));

const allJobs = computed(() => store.state?.jobs || []);
const queueJobs = computed(() => allJobs.value.filter((job) => queueStatuses.has(job.status)));
const completedJobCount = computed(() =>
  [...completedStatuses].reduce((sum, status) => sum + Number(jobStatusCounts.value[status] || 0), 0)
);

function jobStageLabel(job: { status: string; staged?: boolean; progress?: { uploaded?: number } }): string {
  if (job.status === 'running') {
    if (job.staged) return '等待上传';
    if (!(job.progress?.uploaded || 0)) return '下载中';
    return '上传中';
  }
  const map: Record<string, string> = { queued: '排队', done: '完成', failed: '失败', retry: '重试', skipped: '跳过', cancelled: '已取消' };
  return map[job.status] || job.status;
}

function jobStageColor(job: { status: string; staged?: boolean; progress?: { uploaded?: number } }): string {
  if (job.status === 'running') {
    if (job.staged) return 'cyan';
    if (!(job.progress?.uploaded || 0)) return 'green';
    return 'blue';
  }
  return job.status === 'done' ? 'green' : job.status === 'failed' ? 'red' : job.status === 'retry' ? 'orange' : 'default';
}

function profileUsed(profile: { quotaTotal?: number; quotaRemaining?: number; quotaUsed?: number }) {
  const used = Number(profile.quotaUsed || 0);
  if (used > 0) return used;
  return Math.max(0, Number(profile.quotaTotal || 0) - Number(profile.quotaRemaining || 0));
}

function profileRemaining(profile: { quotaTotal?: number; quotaRemaining?: number; quotaUsed?: number }) {
  const remaining = Number(profile.quotaRemaining || 0);
  if (remaining > 0) return remaining;
  return Math.max(0, Number(profile.quotaTotal || 0) - Number(profile.quotaUsed || 0));
}

function quotaPercent(profile: { quotaTotal?: number; quotaRemaining?: number; quotaUsed?: number }) {
  if (!profile.quotaTotal) return 0;
  return Math.min(100, Math.round((profileUsed(profile) / profile.quotaTotal) * 100));
}

function formatBytes(bytes: number) {
  if (!bytes || bytes < 0) return { value: 0, unit: 'B' };
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = bytes, u = 0;
  while (v >= 1024 && u < units.length - 1) { v /= 1024; u++; }
  const value = u === units.length - 1
    ? v.toFixed(2)
    : v.toFixed(v >= 10 || u === 0 ? 0 : 1);
  return { value, unit: units[u] };
}
function fmt(bytes: number) {
  const r = formatBytes(bytes);
  return `${r.value} ${r.unit}`;
}

function formatSpeedParts(bytesPerSec: number) {
  if (!bytesPerSec || bytesPerSec < 0) return { value: '-', unit: '' };
  const units = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
  let v = bytesPerSec, u = 0;
  while (v >= 1024 && u < units.length - 1) { v /= 1024; u++; }
  return { value: v.toFixed(u === 0 || v >= 10 ? 0 : 1), unit: units[u] };
}

function formatSpeed(bytesPerSec: number) {
  const result = formatSpeedParts(bytesPerSec);
  return result.unit ? `${result.value} ${result.unit}` : '0 B/s';
}

async function refresh() {
  refreshing.value = true;
  await store.loadState();
  refreshing.value = false;
}

async function triggerProcess() {
  try { await transfersApi.processJobs(); await store.loadState(); } catch (err) { store.showError(err); }
}

async function deleteJob(jobId: string) {
  deletingJobIds.value.add(jobId);
  try {
    await transfersApi.deleteJob(jobId);
    if (store.state) {
      store.state = { ...store.state, jobs: store.state.jobs.filter((job) => job.id !== jobId) };
    }
    await store.loadState();
  } catch (err) {
    store.showError(err);
  } finally {
    deletingJobIds.value.delete(jobId);
  }
}

async function clearCompletedJobs() {
  try {
    await transfersApi.clearCompletedJobs();
    if (store.state) {
      store.state = { ...store.state, jobs: store.state.jobs.filter((job) => !completedStatuses.has(job.status)) };
    }
    await store.loadState();
  } catch (err) {
    store.showError(err);
  }
}

async function refreshAllCapacity() {
  refreshingCapacity.value = true;
  try {
    const result = await capacityApi.refreshAll();
    await store.loadState();
  } catch (err) {
    store.showError(err);
  } finally {
    refreshingCapacity.value = false;
  }
}
</script>

<style scoped>
.metric-card {
  min-width: 0;
  text-align: center;
}

.metric-title {
  color: var(--color-text-muted);
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
}

.metric-value {
  color: var(--color-text);
  font-size: 20px;
  font-weight: 600;
  line-height: 28px;
  white-space: nowrap;
}

.metric-value span {
  margin-left: 2px;
  font-size: 12px;
  font-weight: 500;
}

.metric-primary {
  color: #1677ff;
}

.metric-sub {
  color: var(--color-text-muted);
  font-size: 11px;
  line-height: 16px;
  overflow: hidden;
}

.metric-sub-status {
  display: flex;
  flex-direction: column;
  gap: 1px;
  white-space: normal;
}

.metric-sub-status span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
