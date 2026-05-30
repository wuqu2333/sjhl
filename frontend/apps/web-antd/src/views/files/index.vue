<template>
  <div class="space-y-4">
    <a-card title="SP 文件浏览">
      <a-form layout="vertical">
        <div class="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-3 items-end">
          <a-form-item label="SP">
            <a-select
              v-model:value="selectedProfileId"
              :options="profileOptions"
              placeholder="选择一个 SP"
              show-search
              option-filter-prop="label"
              @change="onProfileChange"
            />
          </a-form-item>
          <a-form-item label="路径">
            <a-input-search v-model:value="currentPath" enter-button="打开" placeholder="留空表示根目录" @search="loadFiles" />
          </a-form-item>
          <a-form-item label="操作">
            <a-space>
              <a-button @click="openDriveRoot" :disabled="!selectedProfileId">根目录</a-button>
              <a-button @click="openUploadRoot" :disabled="!selectedProfileId">上传目录</a-button>
              <a-button @click="goParent" :disabled="!currentPath">上级</a-button>
              <a-button @click="loadFiles" :loading="loading">刷新</a-button>
            </a-space>
          </a-form-item>
        </div>
      </a-form>

      <div v-if="selectedProfileId" class="space-y-2 mb-3">
        <div class="flex gap-2">
          <a-input-search v-model:value="searchQuery" placeholder="搜索文件" @search="doSearch" :loading="loading" allow-clear />
          <a-button @click="loadFiles" size="small">清除搜索</a-button>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-[1fr_auto_auto] gap-2">
          <a-input v-model:value="newFolderName" placeholder="新文件夹名称" allow-clear @press-enter="createFolder" />
          <a-button type="primary" :loading="creatingFolder" @click="createFolder">新建文件夹</a-button>
          <a-upload :show-upload-list="false" :before-upload="uploadPickedFile" accept="*/*">
            <a-button :loading="uploading">上传文件</a-button>
          </a-upload>
        </div>
      </div>

      <a-alert
        v-if="!selectedProfileId"
        type="info"
        show-icon
        message="先在 SP 容量池中导入或新增 SP，然后选择一个 SP 浏览文件。"
      />
      <a-alert
        v-else-if="!items.length && !loading"
        class="mb-3"
        type="info"
        show-icon
        :message="currentPath ? `当前目录 ${currentPath} 为空，点“根目录”可查看 Drive 根目录。` : '当前根目录为空。'"
      />

      <ResponsiveTable
        v-if="selectedProfileId"
        :columns="columns"
        :data-source="items"
        :loading="loading"
        row-key="id"
        size="small"
        :pagination="{ pageSize: 20 }"
        :scroll="{ x: 900 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <a-button v-if="record.type === 'folder'" type="link" class="!h-auto !p-0 !whitespace-normal !text-left" @click="openFolder(record.path)">
              {{ record.name }}
            </a-button>
            <span v-else class="inline-block max-w-full break-all overflow-wrap-anywhere">{{ record.name }}</span>
          </template>
          <template v-if="column.key === 'type'">
            <a-tag :color="record.type === 'folder' ? 'blue' : 'default'">{{ record.type === 'folder' ? '文件夹' : '文件' }}</a-tag>
          </template>
          <template v-if="column.key === 'size'">
            {{ record.type === 'folder' ? `${record.childCount || 0} 项` : formatSize(record.size) }}
          </template>
          <template v-if="column.key === 'action'">
            <a-space>
              <a-button v-if="record.type === 'folder'" size="small" @click="openFolder(record.path)">进入</a-button>
              <a-button v-if="record.webUrl" size="small" :href="record.webUrl" target="_blank">打开</a-button>
              <a-button v-if="record.downloadUrl" size="small" :href="record.downloadUrl" target="_blank">下载</a-button>
              <a-button size="small" danger @click="deleteFile(record)">删除</a-button>
            </a-space>
          </template>
        </template>
        <template #mobileCard="{ record }">
          <div class="flex items-center justify-between gap-2.5" @click="record.type === 'folder' && openFolder(record.path)">
            <div class="min-w-0 grid gap-0.5">
              <strong class="text-[15px] leading-snug text-gray-900 break-words overflow-wrap-anywhere">{{ record.name }}</strong>
              <span class="text-xs text-gray-500">{{ record.type === 'folder' ? `${record.childCount || 0} 项` : formatSize(record.size) }}</span>
            </div>
            <a-space @click.stop>
              <a-button v-if="record.type === 'folder'" size="small" @click="openFolder(record.path)">进入</a-button>
              <a-button v-if="record.webUrl" size="small" :href="record.webUrl" target="_blank">打开</a-button>
              <a-button v-if="record.downloadUrl" size="small" :href="record.downloadUrl" target="_blank">下载</a-button>
              <a-button size="small" danger @click="deleteFile(record)">删除</a-button>
            </a-space>
          </div>
        </template>
      </ResponsiveTable>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import { useAppStore } from '../../stores/useAppStore';
import { filesApi, type DriveFileItem } from '../../api/files';
import ResponsiveTable from '../../components/common/ResponsiveTable.vue';

const store = useAppStore();
const route = useRoute();
const router = useRouter();
const selectedProfileId = ref('');
const currentPath = ref('');
const loading = ref(false);
const uploading = ref(false);
const creatingFolder = ref(false);
const newFolderName = ref('');
const items = ref<DriveFileItem[]>([]);
const searchQuery = ref('');
let loadSeq = 0;

async function doSearch() {
  if (!selectedProfileId.value || !searchQuery.value) return;
  loading.value = true;
  try {
    const result = await filesApi.search(selectedProfileId.value, searchQuery.value);
    items.value = result.items.map((i: any) => ({
      id: i.id, driveId: i.driveId, name: i.name, type: i.isDir ? 'folder' : 'file', size: i.size,
      path: i.path || '', childCount: 0, mimeType: '', lastModifiedDateTime: i.lastModifiedDateTime,
      webUrl: i.webUrl || '', downloadUrl: '', sha1: '', sha256: '', quickXorHash: ''
    }));
  } catch (err) { store.showError(err); }
  finally { loading.value = false; }
}

async function deleteFile(record: DriveFileItem) {
  if (!selectedProfileId.value) return;
  loading.value = true;
  try {
    await filesApi.deleteItem(selectedProfileId.value, record.id, record.driveId || '', record.path || '', record.type || 'file');
    message.success('已删除');
    await loadFiles();
  } catch (err) { store.showError(err); }
  finally { loading.value = false; }
}

const profileOptions = computed(() =>
  (store.state?.profiles || []).map((item) => ({
    label: item.name,
    value: item.id
  }))
);
const selectedProfile = computed(() =>
  (store.state?.profiles || []).find((item) => item.id === selectedProfileId.value)
);

const columns = [
  { title: '名称', key: 'name', width: 280 },
  { title: '类型', key: 'type', width: 110 },
  { title: '大小', key: 'size', width: 120 },
  { title: '修改时间', dataIndex: 'lastModifiedDateTime', width: 210 },
  { title: '路径', dataIndex: 'path', ellipsis: true },
  { title: '操作', key: 'action', width: 180, fixed: 'right' }
];

watch(
  () => [store.state?.profiles, route.query.profileId, route.query.path],
  () => {
    const profiles = store.state?.profiles || [];
    if (!profiles.length) return;
    const queryProfileId = String(route.query.profileId || '');
    const nextProfileId = profiles.some((item) => item.id === queryProfileId) ? queryProfileId : selectedProfileId.value || profiles[0].id;
    const hasQueryPath = typeof route.query.path === 'string';
    const nextPath = hasQueryPath ? String(route.query.path || '') : currentPath.value;
    const changed = selectedProfileId.value !== nextProfileId || currentPath.value !== nextPath;
    selectedProfileId.value = nextProfileId;
    currentPath.value = normalizePath(nextPath);
    if (changed) loadFiles();
  },
  { immediate: true }
);

async function loadFiles() {
  if (!selectedProfileId.value) {
    items.value = [];
    return;
  }
  const seq = ++loadSeq;
  const profileId = selectedProfileId.value;
  const path = currentPath.value;
  loading.value = true;
  try {
    const result = await filesApi.children(profileId, path);
    if (seq !== loadSeq || profileId !== selectedProfileId.value) return;
    currentPath.value = result.path;
    items.value = result.items;
    updateRouteQuery();
  } catch (err) {
    store.showError(err);
  } finally {
    loading.value = false;
  }
}

function openDriveRoot() {
  currentPath.value = '';
  loadFiles();
}

async function onProfileChange(profileId: string) {
  if (!profileId) return;
  selectedProfileId.value = profileId;
  currentPath.value = '';
  searchQuery.value = '';
  items.value = [];
  updateRouteQuery();
  await loadFiles();
}

function openUploadRoot() {
  currentPath.value = normalizePath(selectedProfile.value?.rootPath || '');
  loadFiles();
}

function openFolder(path: string) {
  currentPath.value = normalizePath(path);
  loadFiles();
}

function goParent() {
  const parts = currentPath.value.split('/').filter(Boolean);
  parts.pop();
  currentPath.value = parts.join('/');
  loadFiles();
}

async function createFolder() {
  if (!selectedProfileId.value || !newFolderName.value.trim()) return;
  creatingFolder.value = true;
  try {
    await filesApi.createFolder(selectedProfileId.value, {
      path: currentPath.value,
      name: newFolderName.value.trim(),
      conflictBehavior: 'rename'
    });
    message.success('文件夹已创建');
    newFolderName.value = '';
    await loadFiles();
  } catch (err) {
    store.showError(err);
  } finally {
    creatingFolder.value = false;
  }
}

async function uploadPickedFile(file: File) {
  if (!selectedProfileId.value) return false;
  uploading.value = true;
  try {
    await filesApi.upload(selectedProfileId.value, currentPath.value, file);
    message.success('上传完成');
    await loadFiles();
  } catch (err) {
    store.showError(err);
  } finally {
    uploading.value = false;
  }
  return false;
}

function updateRouteQuery() {
  const nextQuery = {
    profileId: selectedProfileId.value,
    ...(currentPath.value ? { path: currentPath.value } : {})
  };
  if (String(route.query.profileId || '') === nextQuery.profileId && String(route.query.path || '') === String(nextQuery.path || '')) {
    return;
  }
  router.replace({
    path: '/files',
    query: nextQuery
  });
}

function normalizePath(value: string) {
  return String(value || '').replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
}

function formatSize(size: number) {
  if (!size) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = size;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}
</script>
