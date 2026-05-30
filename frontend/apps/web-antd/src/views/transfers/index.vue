<template>
  <div class="space-y-4">
    <a-tabs v-model:activeKey="activeTab">
      <!-- Tab: 同步作业 -->
      <a-tab-pane key="sync" tab="同步作业">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <a-card title="新建/编辑同步作业">
            <a-form layout="vertical" :model="syncForm" @finish="submitSync">
              <a-form-item label="名称"><a-input v-model:value="syncForm.name" /></a-form-item>
              <a-form-item label="目标容量池 / SP"><a-select v-model:value="syncForm.profileId" :options="profileOptions" /></a-form-item>
              <a-form-item label="115 账号"><a-select v-model:value="syncForm.pan115AccountId" :options="pan115AccountOptions" placeholder="选择账号" /></a-form-item>
              <a-form-item label="源类型"><a-select v-model:value="syncForm.sourceType" :options="syncSourceOptions" /></a-form-item>
              <a-form-item v-if="syncForm.sourceType === 'local'" label="本地源路径"><a-input v-model:value="syncForm.sourcePath" /></a-form-item>
              <a-form-item v-if="syncForm.sourceType === '115-cookie'" label="115 CID">
                <a-input-search v-model:value="syncForm.sourceCid" placeholder="在115浏览中点击目录自动填入" search-button @search="activeTab='browse'">
                  <template #enterButton><a-button>浏览选择</a-button></template>
                </a-input-search>
              </a-form-item>
              <a-form-item label="SP 目标目录"><a-input v-model:value="syncForm.targetDir" placeholder="留空则自动使用115目录名" /></a-form-item>
              <a-form-item label="模式"><a-select v-model:value="syncForm.syncMode" :options="syncModeOptions" /></a-form-item>
              <a-form-item label="定时任务"><a-checkbox v-model:checked="syncForm.enabled">启用自动同步</a-checkbox></a-form-item>
              <a-form-item v-if="syncForm.enabled" label="每天定时">
                <a-input v-model:value="syncForm.scheduleTime" placeholder="HH:mm，例如 03:30" />
              </a-form-item>
              <a-form-item v-if="syncForm.enabled" label="间隔分钟">
                <a-input-number v-model:value="syncForm.intervalMinutes" :min="0" class="w-full" placeholder="0 表示不按间隔执行" />
              </a-form-item>
              <a-form-item><a-checkbox v-model:checked="syncForm.recursive">递归源目录</a-checkbox></a-form-item>
              <a-button type="primary" html-type="submit" block>保存作业</a-button>
            </a-form>
          </a-card>
          <a-card title="作业列表">
            <div v-if="!store.state?.syncJobs?.length" class="text-gray-400 text-sm">暂无同步作业</div>
            <div v-for="item in store.state?.syncJobs || []" :key="item.id" class="mb-3 p-3 border border-border rounded-lg">
              <div class="flex items-center justify-between mb-1">
                <strong class="text-sm">{{ item.name }}</strong>
                <a-space>
                  <a-tag :color="item.lastStatus === 'running' ? 'blue' : item.lastStatus === 'failed' ? 'red' : item.lastStatus === 'done' ? 'green' : 'default'">{{ item.lastStatus || '空闲' }}</a-tag>
                  <a-button size="small" @click="runSync(item.id)">运行</a-button>
                  <a-button size="small" danger @click="removeSync(item.id)">删除</a-button>
                </a-space>
              </div>
              <div class="text-xs text-gray-500 mb-1">{{ item.sourceType }} → {{ item.targetDir || '/' }}</div>
              <div class="text-xs text-gray-500 mb-1">
                <a-tag size="small" :color="item.enabled ? 'blue' : 'default'">{{ scheduleText(item) }}</a-tag>
                <span v-if="item.nextRunAt">下次: {{ formatDateTime(item.nextRunAt) }}</span>
              </div>
              <div v-if="item.lastError" class="text-xs text-red-500 mb-1">错误: {{ item.lastError }}</div>
              <div v-if="item.logs?.length" class="text-xs text-gray-400 max-h-24 overflow-y-auto bg-gray-50 rounded p-1 font-mono">
                <div v-for="(log, idx) in item.logs.slice(-10).reverse()" :key="idx">{{ log.at?.slice(11,19) }} {{ log.message }}</div>
              </div>
            </div>
          </a-card>
        </div>
      </a-tab-pane>

      <!-- Tab 3: 115 浏览 -->
      <a-tab-pane key="browse" tab="115 浏览">
        <a-card title="115 目录浏览" size="small">
          <div class="flex gap-2 mb-2 flex-wrap">
            <a-select v-model:value="pan115AccountId" :options="pan115AccountOptions" placeholder="115 账号" class="w-36" @change="on115AccountChange" />
            <a-select v-model:value="pan115TargetProfile" :options="spOnlyOptions" placeholder="目标 SP" class="w-36" />
            <a-button size="small" :loading="pan115Loading" @click="openPan115Root">根目录</a-button>
            <a-button size="small" :disabled="pan115CurrentCid === '0'" @click="openPan115Parent">上级</a-button>
          </div>
          <div class="flex gap-2 mb-2">
            <a-input-search v-model:value="pan115Search" placeholder="搜索文件" size="small" @search="doSearch" :loading="pan115Loading" allow-clear class="flex-1" />
            <a-input v-model:value="pan115NewFolder" placeholder="新文件夹名" size="small" class="w-32" />
            <a-button size="small" @click="create115Folder">新建</a-button>
          </div>
          <a-alert v-if="!pan115AccountId" type="info" show-icon message="先到设置页添加 115 账号，再选择账号和目标 SP，点击「根目录」开始浏览" class="mb-3" />
          <div v-if="pan115Path.length" class="flex gap-2 mb-3 text-sm text-gray-500">
            <a-button size="small" @click="openPan115Root">根目录</a-button>
            <span v-for="(dir, idx) in pan115Path" :key="`${dir.cid}-${idx}`" class="flex items-center gap-1">
              <span>/</span>
              <a-button size="small" type="link" @click="openPan115Breadcrumb(idx)">{{ dir.name }}</a-button>
            </span>
          </div>
          <a-empty v-if="!pan115Items.length && !pan115Loading" description="点击根目录加载" :image-style="{ height: '48px' }" />
          <div v-else class="space-y-1">
            <div v-for="item in pan115Items" :key="item.fid" class="flex items-center justify-between p-2 rounded hover:bg-gray-50 border border-border">
              <div class="min-w-0 flex-1 flex items-center gap-2" :class="item.isDir ? 'cursor-pointer' : ''" @click="item.isDir && enterDir(item)">
                <span :class="item.isDir ? 'text-blue-500' : 'text-gray-400'">{{ item.isDir ? 'D' : 'F' }}</span>
                <span :class="item.isDir ? 'text-blue-600 cursor-pointer' : ''" class="truncate">{{ item.name }}</span>
              </div>
              <span class="text-xs text-gray-400 mx-2 shrink-0">{{ item.isDir ? '-' : format115Size(item.size) }}</span>
              <a-space>
                <a-button v-if="item.isDir" size="small" type="primary" @click="transfer115Folder(item)">搬运</a-button>
                <a-button v-if="item.isDir" size="small" @click="useAsSyncSource(item)">同步</a-button>
                <a-button v-if="!item.isDir" size="small" danger @click="delete115Item(item)">删除</a-button>
              </a-space>
            </div>
          </div>
        </a-card>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useAppStore } from '../../stores/useAppStore';
import { transfersApi } from '../../api/transfers';
import { syncJobsApi } from '../../api/sync-jobs';
import { pan115Api, type Pan115Item, type Pan115Account } from '../../api/pan115';

const store = useAppStore();
const activeTab = ref<'sync' | 'browse'>('sync');
const AUTO = '__auto_capacity_pool__';
const POOL_PREFIX = '__capacity_pool__:';
const DEFAULT_CAPACITY_POOL_ID = 'default';
const TRANSFER_STATE_KEY = 'sjhl:transfers-state-v1';
type Pan115PathEntry = { name: string; cid: string };

function capacityPoolOptionValue(poolId: string) {
  return poolId === DEFAULT_CAPACITY_POOL_ID ? AUTO : `${POOL_PREFIX}${poolId}`;
}

const profileOptions = computed(() => {
  const pools = store.state?.capacityPools?.length
    ? store.state.capacityPools
    : [{ id: DEFAULT_CAPACITY_POOL_ID, name: '默认容量池' }];
  return [
    ...pools.map((pool) => ({ label: `容量池 / ${pool.name}`, value: capacityPoolOptionValue(pool.id) })),
    ...((store.state?.profiles || []).map((item) => ({ label: `SP / ${item.name}`, value: item.id }))),
  ];
});
const spOnlyOptions = computed(() =>
  (store.state?.profiles || []).map((item) => ({ label: item.name, value: item.id }))
);

// --- Sync form ---
const syncSourceOptions = [{ label: '本地目录', value: 'local' }, { label: '115 Cookie 目录', value: '115-cookie' }];
const syncModeOptions = [{ label: '仅新增', value: 'add' }, { label: '全同步上传变更', value: 'full' }];
const syncForm = reactive({
  name: '',
  profileId: AUTO,
  pan115AccountId: '',
  sourceType: 'local',
  sourcePath: '',
  sourceCid: '0',
  targetDir: '',
  syncMode: 'add',
  recursive: true,
  dedupeScope: 'global',
  enabled: false,
  intervalMinutes: 0,
  scheduleTime: '',
});

function scheduleText(item: any) {
  if (!item.enabled) return '未启用定时';
  const parts: string[] = [];
  if (item.scheduleTime) parts.push(`每天 ${item.scheduleTime}`);
  if (Number(item.intervalMinutes || 0) > 0) parts.push(`每 ${item.intervalMinutes} 分钟`);
  return parts.length ? parts.join(' / ') : '已启用';
}

function formatDateTime(value: string) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

// --- Sync actions ---
async function submitSync() {
  const data: Record<string, unknown> = { ...syncForm };
  if (data.sourceType === '115-cookie') delete (data as any).cookie;
  try { await syncJobsApi.save(data); store.loadState(); } catch (err) { store.showError(err); }
}
async function runSync(id: string) { await syncJobsApi.run(id); store.loadState(); }
async function removeSync(id: string) { await syncJobsApi.remove(id); store.loadState(); }

// --- 115 Browse ---
const pan115Accounts = ref<Pan115Account[]>([]);
const pan115AccountId = ref('');
const pan115TargetProfile = ref('');
const pan115Loading = ref(false);
const pan115Items = ref<Pan115Item[]>([]);
const pan115Path = ref<Pan115PathEntry[]>([]);
const pan115CurrentCid = ref('0');

const pan115AccountOptions = computed(() => pan115Accounts.value.map((a) => ({ label: a.name, value: a.id })));

async function load115Accounts() { try { pan115Accounts.value = (await pan115Api.listAccounts()).accounts; } catch (err) { store.showError(err); } }
function on115AccountChange() {
  pan115CurrentCid.value = '0';
  pan115Path.value = [];
  pan115Items.value = [];
}

function normalizePan115Cid(cid: string | number | null | undefined) {
  const value = String(cid ?? '').trim();
  return value || '0';
}

async function browsePan115(cid: string, nextPath?: Pan115PathEntry[]) {
  if (!pan115AccountId.value) return;
  const targetCid = normalizePan115Cid(cid);
  pan115Loading.value = true;
  try {
    const r = await pan115Api.listDir(pan115AccountId.value, targetCid);
    pan115Items.value = r.items;
    pan115CurrentCid.value = targetCid;
    if (targetCid === '0') {
      pan115Path.value = [];
    } else if (nextPath) {
      pan115Path.value = nextPath;
    } else {
      const existingIndex = pan115Path.value.findIndex((dir) => normalizePan115Cid(dir.cid) === targetCid);
      if (existingIndex >= 0) {
        pan115Path.value = pan115Path.value.slice(0, existingIndex + 1);
      }
    }
  } catch (err) { store.showError(err); }
  finally { pan115Loading.value = false; }
}

function openPan115Root() {
  browsePan115('0', []);
}

function openPan115Parent() {
  if (!pan115Path.value.length) {
    openPan115Root();
    return;
  }
  const nextPath = pan115Path.value.slice(0, -1);
  const parent = nextPath[nextPath.length - 1];
  browsePan115(parent?.cid || '0', nextPath);
}

function openPan115Breadcrumb(index: number) {
  const target = pan115Path.value[index];
  if (!target) return;
  browsePan115(target.cid, pan115Path.value.slice(0, index + 1));
}

function enterDir(item: Pan115Item) {
  const targetCid = normalizePan115Cid(item.cid || item.fid);
  const existingIndex = pan115Path.value.findIndex((dir) => normalizePan115Cid(dir.cid) === targetCid);
  const nextPath = existingIndex >= 0
    ? pan115Path.value.slice(0, existingIndex + 1)
    : [...pan115Path.value, { name: item.name, cid: targetCid }];
  browsePan115(targetCid, nextPath);
}
function format115Size(size: number) { if (!size) return '0 B'; const u = ['B','KB','MB','GB','TB']; let v = size, i = 0; while (v >= 1024 && i < u.length-1) { v /= 1024; i++; } return `${v.toFixed(v>=10||i===0?0:1)} ${u[i]}`; }



const pan115PathText = computed(() => pan115Path.value.map((d) => d.name).join('/'));
const pan115Search = ref('');
const pan115NewFolder = ref('');

function readPersistedTransferState(): Record<string, any> | null {
  try {
    const raw = localStorage.getItem(TRANSFER_STATE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

function sanitizePan115Path(value: unknown): Pan115PathEntry[] {
  if (!Array.isArray(value)) return [];
  const result: Pan115PathEntry[] = [];
  for (const item of value) {
    if (!item || typeof item !== 'object') continue;
    const raw = item as Record<string, unknown>;
    const name = typeof raw.name === 'string' ? raw.name.trim() : '';
    const cid = normalizePan115Cid(raw.cid as string | number | null | undefined);
    if (!name || !cid) continue;
    if (result.some((dir) => normalizePan115Cid(dir.cid) === cid)) continue;
    result.push({ name, cid });
  }
  return result;
}

function restoreTransferState() {
  const saved = readPersistedTransferState();
  if (!saved) return;
  if (saved.activeTab === 'sync' || saved.activeTab === 'browse') {
    activeTab.value = saved.activeTab;
  }
  if (saved.syncForm && typeof saved.syncForm === 'object') {
    const form = saved.syncForm as Record<string, unknown>;
    Object.assign(syncForm, {
      name: typeof form.name === 'string' ? form.name : syncForm.name,
      profileId: typeof form.profileId === 'string' ? form.profileId : syncForm.profileId,
      pan115AccountId: typeof form.pan115AccountId === 'string' ? form.pan115AccountId : syncForm.pan115AccountId,
      sourceType: form.sourceType === '115-cookie' || form.sourceType === 'local' ? form.sourceType : syncForm.sourceType,
      sourcePath: typeof form.sourcePath === 'string' ? form.sourcePath : syncForm.sourcePath,
      sourceCid: typeof form.sourceCid === 'string' ? form.sourceCid : syncForm.sourceCid,
      targetDir: typeof form.targetDir === 'string' ? form.targetDir : syncForm.targetDir,
      syncMode: form.syncMode === 'full' || form.syncMode === 'add' ? form.syncMode : syncForm.syncMode,
      recursive: typeof form.recursive === 'boolean' ? form.recursive : syncForm.recursive,
      enabled: typeof form.enabled === 'boolean' ? form.enabled : syncForm.enabled,
      intervalMinutes: Number.isFinite(Number(form.intervalMinutes)) ? Number(form.intervalMinutes) : syncForm.intervalMinutes,
      scheduleTime: typeof form.scheduleTime === 'string' ? form.scheduleTime : syncForm.scheduleTime,
    });
  }
  pan115AccountId.value = typeof saved.pan115AccountId === 'string' ? saved.pan115AccountId : pan115AccountId.value;
  pan115TargetProfile.value = typeof saved.pan115TargetProfile === 'string' ? saved.pan115TargetProfile : pan115TargetProfile.value;
  pan115CurrentCid.value = normalizePan115Cid(saved.pan115CurrentCid);
  pan115Path.value = sanitizePan115Path(saved.pan115Path);
  pan115Search.value = typeof saved.pan115Search === 'string' ? saved.pan115Search : pan115Search.value;
}

function persistTransferState() {
  localStorage.setItem(TRANSFER_STATE_KEY, JSON.stringify({
    activeTab: activeTab.value,
    syncForm: { ...syncForm },
    pan115AccountId: pan115AccountId.value,
    pan115TargetProfile: pan115TargetProfile.value,
    pan115CurrentCid: pan115CurrentCid.value,
    pan115Path: pan115Path.value,
    pan115Search: pan115Search.value,
  }));
}

restoreTransferState();

watch(
  [
    activeTab,
    () => ({ ...syncForm }),
    pan115AccountId,
    pan115TargetProfile,
    pan115CurrentCid,
    pan115Path,
    pan115Search,
  ],
  () => persistTransferState(),
  { deep: true }
);

async function doSearch() {
  if (!pan115AccountId.value || !pan115Search.value) return;
  pan115Loading.value = true;
  try {
    const r = await pan115Api.searchFiles(pan115AccountId.value, pan115Search.value);
    pan115Items.value = r.items.map((i: any) => ({
      fid: i.fileId,
      cid: i.isDir ? i.fileId : i.parentId,
      name: i.fileName,
      size: i.size,
      isDir: i.isDir,
      pickCode: i.pickCode,
      sha1: i.sha1,
      mtime: i.updateTime
    }));
  } catch (err) { store.showError(err); }
  finally { pan115Loading.value = false; }
}

async function create115Folder() {
  if (!pan115AccountId.value || !pan115NewFolder.value) return;
  pan115Loading.value = true;
  try {
    const currentCid = pan115CurrentCid.value;
    await pan115Api.createFolder(pan115AccountId.value, currentCid, pan115NewFolder.value);
    pan115NewFolder.value = '';
    await browsePan115(currentCid, pan115Path.value);
  } catch (err) { store.showError(err); }
  finally { pan115Loading.value = false; }
}

async function delete115Item(item: Pan115Item) {
  if (!pan115AccountId.value) return;
  pan115Loading.value = true;
  try {
    await pan115Api.deleteFiles(pan115AccountId.value, [item.fid]);
    await browsePan115(pan115CurrentCid.value, pan115Path.value);
  } catch (err) { store.showError(err); }
  finally { pan115Loading.value = false; }
}

async function transfer115Folder(item: Pan115Item) {
  if (!pan115TargetProfile.value || !pan115AccountId.value) { store.showError(new Error('请选择目标 SP 和 115 账号')); return; }
  pan115Loading.value = true;
  try {
    await transfersApi.upload115Folder({ accountId: pan115AccountId.value, sourceCid: item.cid, profileId: pan115TargetProfile.value, remoteDir: pan115PathText.value });
    store.loadState();
  } catch (err) { store.showError(err); }
  finally { pan115Loading.value = false; }
}

function useAsSyncSource(item: Pan115Item) {
  syncForm.pan115AccountId = pan115AccountId.value;
  syncForm.sourceType = '115-cookie';
  syncForm.sourceCid = item.cid;
  syncForm.targetDir = pan115PathText.value ? pan115PathText.value + '/' + item.name : item.name;
  syncForm.name = syncForm.name || item.name;
  activeTab.value = 'sync';
}

onMounted(async () => {
  await load115Accounts();
  if (pan115AccountId.value && activeTab.value === 'browse') {
    await browsePan115(pan115CurrentCid.value, pan115Path.value);
  }
});
</script>
