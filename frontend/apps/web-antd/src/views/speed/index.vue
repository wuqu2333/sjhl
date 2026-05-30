<template>
  <div class="speed-page">
    <!-- 总速率卡片 -->
    <div class="total-speed-card">
      <div class="speed-row">
        <div class="speed-col" v-if="totalUploadSpeed > 0">
          <div class="speed-label">上传</div>
          <div class="speed-value">{{ formatSpeedParts(totalUploadSpeed).value }}</div>
          <div class="speed-unit">{{ formatSpeedParts(totalUploadSpeed).unit }}/s</div>
        </div>
        <div class="speed-col" v-if="totalDownloadSpeed > 0">
          <div class="speed-label down">下载</div>
          <div class="speed-value down">{{ formatSpeedParts(totalDownloadSpeed).value }}</div>
          <div class="speed-unit">{{ formatSpeedParts(totalDownloadSpeed).unit }}/s</div>
        </div>
        <div class="speed-col" v-if="totalUploadSpeed <= 0 && totalDownloadSpeed <= 0">
          <div class="speed-value" style="font-size: 32px">—</div>
          <div class="speed-unit">等待传输</div>
        </div>
      </div>
      <div class="speed-meta">
        运行中 {{ runningCount }} 个任务 · 今日上传 {{ formatBytes(store.state?.stats?.todayUploaded?.totalSize || 0) }}
      </div>
    </div>

    <!-- 速度历史小图 -->
    <div class="chart-card" v-if="speedHistory.length > 1">
      <div class="chart-header">
        <span class="chart-title">实时速率</span>
        <span class="chart-legend">
          <span v-if="totalUploadSpeed > 0" class="dot up"></span> 上传
          <span v-if="totalDownloadSpeed > 0" class="dot down"></span> 下载
        </span>
      </div>
      <canvas ref="chartCanvas" class="speed-chart"></canvas>
    </div>

    <!-- 运行中任务列表 -->
    <div class="jobs-card" v-if="runningJobs.length">
      <div class="card-header">传输中的任务</div>
      <div v-for="job in runningJobs" :key="job.id" class="job-row">
        <div class="job-info">
          <div class="job-name" :title="job.file_name">{{ job.file_name }}</div>
          <div class="job-meta">
            {{ job.profile_name }} · {{ formatBytes(job.size) }}
            <span v-if="job._isDownloading" class="phase-tag down-tag">下载中</span>
            <span v-else class="phase-tag up-tag">上传中</span>
          </div>
          <div class="job-bar">
            <div class="job-bar-fill" :class="{ down: job._isDownloading }" :style="{ width: job.percent + '%' }"></div>
          </div>
          <div class="job-bar-text">
            {{ job.percent }}% · {{ formatBytes(job._isDownloading ? (job.progress?.downloaded || 0) : (job.progress?.uploaded || 0)) }} / {{ formatBytes(job.progress?.total || job.size) }}
          </div>
        </div>
        <div class="job-speeds">
          <div v-if="job._dlSpeed > 0" class="job-speed down-speed">{{ formatSpeedParts(job._dlSpeed).value }} <small>{{ formatSpeedParts(job._dlSpeed).unit }}/s</small></div>
          <div v-if="job._ulSpeed > 0" class="job-speed up-speed">{{ formatSpeedParts(job._ulSpeed).value }} <small>{{ formatSpeedParts(job._ulSpeed).unit }}/s</small></div>
          <div v-if="job._dlSpeed <= 0 && job._ulSpeed <= 0" class="job-speed" style="color:#999">—</div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div class="empty-card" v-if="!runningJobs.length">
      <div class="empty-icon">📊</div>
      <div class="empty-text">当前没有传输中的任务</div>
      <div class="empty-sub">开始上传后此处将显示实时速率</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { useAppStore } from '../../stores/useAppStore';

const store = useAppStore();
const chartCanvas = ref<HTMLCanvasElement | null>(null);

// ---- 纯响应式速率追踪（无 computed 副作用）----
interface JobSample { uploaded: number; downloaded: number; at: number }
const jobSamples = new Map<string, JobSample>();
const runningJobs = ref<any[]>([]);
const totalUploadSpeed = ref(0);
const totalDownloadSpeed = ref(0);
const runningCount = ref(0);
const speedHistory = ref<{ at: number; up: number; down: number }[]>([]);
const MAX_HISTORY = 60;
const MAX_BPS = 125 * 1024 * 1024; // 1 Gbps sanity cap

// 用 watch 追踪 store.state 变化，每次重新计算所有速率
watch(
  () => store.state?.jobs,
  (jobs) => {
    if (!jobs) return;
    const now = Date.now();
    let totalUp = 0;
    let totalDown = 0;
    const active = new Map<string, any>();

    const running = jobs.filter((j: any) => j.status === 'running');
    runningCount.value = running.length;

    const enriched = running.map((j: any) => {
      const id = j.id;
      const prog = j.progress || {};
      const uploaded = prog.uploaded || 0;
      const downloaded = prog.downloaded || 0;

      const prev = jobSamples.get(id);
      let dlSpeed = 0;
      let ulSpeed = 0;

      if (prev) {
        const dt = (now - prev.at) / 1000;
        if (dt >= 1.0 && dt <= 15) {
          // 上传速度：uploaded 变化
          if (uploaded > prev.uploaded) {
            const raw = (uploaded - prev.uploaded) / dt;
            ulSpeed = Math.min(raw, MAX_BPS);
          }
          // 下载速度：downloaded 变化
          if (downloaded > prev.downloaded) {
            const raw = (downloaded - prev.downloaded) / dt;
            dlSpeed = Math.min(raw, MAX_BPS);
          }
        }
      }
      // 记录本次采样
      active.set(id, { uploaded, downloaded, at: now });

      // 判断当前阶段：有下载速度 且 uploaded 还没开始 → 下载中
      const isDownloading = dlSpeed > 0 || (downloaded > 0 && uploaded === 0);

      totalUp += ulSpeed;
      totalDown += dlSpeed;

      return {
        ...j,
        _dlSpeed: dlSpeed,
        _ulSpeed: ulSpeed,
        _isDownloading: isDownloading,
      };
    });

    // 清理已结束任务的采样
    jobSamples.clear();
    for (const [id, sample] of active) {
      jobSamples.set(id, sample);
    }

    runningJobs.value = enriched;
    totalUploadSpeed.value = totalUp;
    totalDownloadSpeed.value = totalDown;

    // 记录历史（最少 1.5 秒间隔）
    const prevHist = speedHistory.value[speedHistory.value.length - 1];
    if (!prevHist || now - prevHist.at > 1500) {
      speedHistory.value.push({ at: now, up: totalUp, down: totalDown });
      if (speedHistory.value.length > MAX_HISTORY) speedHistory.value.shift();
    }
  },
  { deep: true }
);

// 页面隐藏回来时清除采样，避免大跨度 delta
function onVis() {
  if (document.visibilityState === 'visible') jobSamples.clear();
}
document.addEventListener('visibilitychange', onVis);
onBeforeUnmount(() => document.removeEventListener('visibilitychange', onVis));

// ---- 格式化 ----
function formatSpeedParts(bps: number): { value: string; unit: string } {
  if (!bps || bps <= 0) return { value: '0', unit: 'B' };
  if (bps >= 1073741824) return { value: (bps / 1073741824).toFixed(1), unit: 'GB' };
  if (bps >= 1048576) return { value: (bps / 1048576).toFixed(1), unit: 'MB' };
  if (bps >= 1024) return { value: (bps / 1024).toFixed(0), unit: 'KB' };
  return { value: bps.toFixed(0), unit: 'B' };
}

function formatBytes(bytes: number): string {
  if (!bytes) return '0 B';
  if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(2) + ' GB';
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
  if (bytes >= 1024) return (bytes / 1024).toFixed(0) + ' KB';
  return bytes + ' B';
}

// ---- 速度曲线（上下行双线） ----
function drawChart() {
  const canvas = chartCanvas.value;
  if (!canvas) return;
  const data = speedHistory.value;
  if (data.length < 2) return;

  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  const ctx = canvas.getContext('2d')!;
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;
  const pad = { top: 8, right: 8, bottom: 20, left: 8 };
  const ph = h - pad.top - pad.bottom;
  const pw = w - pad.left - pad.right;

  let maxV = 1;
  for (const p of data) maxV = Math.max(maxV, p.up, p.down);
  const niceMax = niceCeil(maxV);

  let unit = 'B/s', divisor = 1;
  if (maxV >= 1073741824) { unit = 'GB/s'; divisor = 1073741824; }
  else if (maxV >= 1048576) { unit = 'MB/s'; divisor = 1048576; }
  else if (maxV >= 1024) { unit = 'KB/s'; divisor = 1024; }

  ctx.clearRect(0, 0, w, h);

  // 网格
  ctx.strokeStyle = '#f0f0f0';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (ph / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(w - pad.right, y);
    ctx.stroke();
    const label = ((niceMax / divisor) * (1 - i / 4)).toFixed(1);
    ctx.fillStyle = '#999';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(label + ' ' + unit, 2, y + 3);
  }

  const xScale = pw / (data.length - 1);
  const yScale = ph / niceMax;

  function drawLine(values: number[], color: string, fillColor: string) {
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    for (let i = 0; i < data.length; i++) {
      const x = pad.left + i * xScale;
      const y = pad.top + ph - values[i] * yScale;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.lineTo(pad.left + (data.length - 1) * xScale, pad.top + ph);
    ctx.lineTo(pad.left, pad.top + ph);
    ctx.closePath();
    ctx.fillStyle = fillColor;
    ctx.fill();
  }

  drawLine(data.map(d => d.down), '#52c41a', 'rgba(82,196,26,0.05)');
  drawLine(data.map(d => d.up), '#1677ff', 'rgba(22,119,255,0.05)');
}

function niceCeil(v: number): number {
  if (v <= 0) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  const norm = v / mag;
  if (norm <= 1) return mag;
  if (norm <= 2) return 2 * mag;
  if (norm <= 5) return 5 * mag;
  return 10 * mag;
}

watch(speedHistory, () => nextTick(drawChart), { deep: false });
</script>

<style scoped>
.speed-page { max-width: 720px; margin: 0 auto; }

.total-speed-card {
  background: linear-gradient(135deg, #1677ff 0%, #4096ff 100%);
  border-radius: 12px; padding: 20px 24px; text-align: center; color: #fff;
  margin-bottom: 12px;
}
.speed-row { display: flex; justify-content: center; gap: 32px; flex-wrap: wrap; }
.speed-col { text-align: center; }
.speed-label { font-size: 12px; opacity: 0.75; margin-bottom: 2px; }
.speed-label.down { color: #b7eb8f; }
.speed-value { font-size: 48px; font-weight: 700; line-height: 1.1; font-family: 'Segoe UI', sans-serif; }
.speed-value.down { color: #b7eb8f; }
.speed-unit { font-size: 13px; opacity: 0.8; margin-top: 2px; }
.speed-meta { font-size: 12px; opacity: 0.65; margin-top: 12px; }

.chart-card { background: #fff; border-radius: 10px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.chart-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.chart-title { font-size: 13px; color: #888; }
.chart-legend { font-size: 11px; color: #999; display: flex; gap: 10px; align-items: center; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
.dot.up { background: #1677ff; }
.dot.down { background: #52c41a; }
.speed-chart { width: 100%; height: 140px; display: block; }

.jobs-card { background: #fff; border-radius: 10px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.card-header { font-size: 13px; color: #888; margin-bottom: 10px; }

.job-row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid #f5f5f5; }
.job-row:last-child { border-bottom: none; }
.job-info { flex: 1; min-width: 0; }
.job-name { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.job-meta { font-size: 11px; color: #999; margin-top: 2px; display: flex; align-items: center; gap: 6px; }
.phase-tag { font-size: 10px; padding: 0 5px; border-radius: 3px; line-height: 18px; }
.down-tag { background: #f6ffed; color: #389e0d; }
.up-tag { background: #e6f7ff; color: #096dd9; }
.job-bar { height: 4px; background: #f0f0f0; border-radius: 2px; margin-top: 6px; }
.job-bar-fill { height: 100%; background: #1677ff; border-radius: 2px; transition: width 0.5s; }
.job-bar-fill.down { background: #52c41a; }
.job-bar-text { font-size: 11px; color: #999; margin-top: 2px; }
.job-speeds { text-align: right; min-width: 75px; }
.job-speed { font-size: 18px; font-weight: 700; line-height: 1.3; }
.job-speed small { font-size: 11px; font-weight: 400; }
.up-speed { color: #1677ff; }
.down-speed { color: #52c41a; }

.empty-card { text-align: center; padding: 60px 20px; }
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty-text { font-size: 15px; color: #666; }
.empty-sub { font-size: 12px; color: #999; margin-top: 6px; }
</style>
