<template>
  <div class="app-root min-h-screen bg-bg">
    <a-layout class="min-h-screen bg-bg">
      <!-- Desktop Sidebar -->
      <a-layout-sider v-if="!store.isMobile" width="232" theme="dark">
        <div class="h-14 flex items-center gap-2.5 px-[18px] text-white font-bold">
          <span class="w-[30px] h-[30px] grid place-items-center rounded-lg bg-primary">SP</span>
          <span>世纪互联管理器</span>
        </div>
        <a-menu
          :selectedKeys="[route.path]"
          theme="dark"
          mode="inline"
          :items="menuItems"
          @click="onMenuClick"
        />
      </a-layout-sider>

      <!-- Mobile Drawer -->
      <a-drawer
        v-model:open="mobileMenuOpen"
        placement="left"
        :width="260"
        :closable="false"
        :body-style="{ padding: 0, background: '#001529' }"
      >
        <div class="h-14 flex items-center gap-2.5 px-[18px] text-white font-bold">
          <span class="w-[30px] h-[30px] grid place-items-center rounded-lg bg-primary">SP</span>
          <span>世纪互联管理器</span>
        </div>
        <a-menu
          :selectedKeys="[route.path]"
          theme="dark"
          mode="inline"
          :items="menuItems"
          @click="onMenuClick"
        />
      </a-drawer>

      <a-layout>
        <!-- Header -->
        <a-layout-header class="flex items-center gap-2 h-10 px-3 bg-white/95 backdrop-blur border-b border-gray-100">
          <a-button v-if="store.isMobile" type="text" class="!w-8 !h-8 shrink-0" @click="mobileMenuOpen = true">
            <MenuOutlined />
          </a-button>
          <span class="text-sm text-gray-500 truncate flex-1">{{ title }}</span>
          <a-button size="small" type="text" @click="store.loadState()">刷新</a-button>
        </a-layout-header>

        <!-- Content -->
        <a-layout-content class="p-2.5 md:p-4 min-w-0 overflow-x-hidden pb-20 md:pb-4">
          <a-alert v-if="store.error" type="error" :message="store.error" show-icon closable @close="store.clearError()" />
          <router-view v-slot="{ Component }">
            <Suspense>
              <component :is="Component" />
              <template #fallback>
                <div class="flex items-center justify-center py-20"><a-spin size="large" /></div>
              </template>
            </Suspense>
          </router-view>
        </a-layout-content>
      </a-layout>
    </a-layout>

    <!-- Mobile Bottom Tab Bar (scrollable, all routes) -->
    <nav v-if="store.isMobile" class="mobile-tabbar">
      <button
        v-for="item in mobileTabs"
        :key="item.path"
        type="button"
        :class="{ active: route.path === item.path }"
        @click="router.push(item.path)"
      >
        <component :is="iconMap[item.meta.icon] || DashboardOutlined" />
        <span class="text-[11px] leading-tight">{{ item.shortTitle || item.meta.title }}</span>
      </button>
    </nav>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  CloudServerOutlined,
  ClusterOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  FolderOpenOutlined,
  LoginOutlined,
  MenuOutlined,
  ProfileOutlined,
  SwapOutlined,
  ThunderboltOutlined
} from '@ant-design/icons-vue';
import { useAppStore } from './stores/useAppStore';
import { routes } from './router/routes';

const iconMap: Record<string, any> = {
  cloud: CloudServerOutlined,
  cluster: ClusterOutlined,
  dashboard: DashboardOutlined,
  database: DatabaseOutlined,
  folder: FolderOpenOutlined,
  login: LoginOutlined,
  profile: ProfileOutlined,
  swap: SwapOutlined,
  thunderbolt: ThunderboltOutlined
};

const router = useRouter();
const route = useRoute();
const store = useAppStore();
const mobileMenuOpen = ref(false);
const LAST_ROUTE_KEY = 'sjhl:last-route';

// Desktop sidebar menu items
const menuItems = computed(() =>
  routes.map((item) => ({
    key: item.path,
    icon: () => h(iconMap[item.meta.icon] || DashboardOutlined),
    label: item.meta.title
  }))
);

// Mobile tab bar: all routes with short labels
const mobileTabs = computed(() =>
  routes.map((item) => ({
    ...item,
    shortTitle:
      item.meta.shortTitle || (item.meta.title.length > 3 ? item.meta.title.slice(0, 3) : item.meta.title)
  }))
);

const title = computed(
  () => routes.find((item) => item.path === route.path)?.meta.title || '总览'
);

function onMenuClick(event: { key: string }) {
  router.push(event.key);
  mobileMenuOpen.value = false;
}

function persistCurrentRoute() {
  if (route.fullPath && route.fullPath !== '/') {
    localStorage.setItem(LAST_ROUTE_KEY, route.fullPath);
  }
}

function restoreLastRoute() {
  if (route.fullPath !== '/') return;
  const lastRoute = localStorage.getItem(LAST_ROUTE_KEY);
  if (lastRoute && lastRoute !== '/') {
    router.replace(lastRoute).catch(() => undefined);
  }
}

function onPageShow(event: PageTransitionEvent) {
  if (event.persisted) {
    store.scheduleResumeRefresh();
  }
}

watch(
  () => route.fullPath,
  () => persistCurrentRoute()
);

onMounted(() => {
  restoreLastRoute();
  persistCurrentRoute();
  store.loadState();
  window.addEventListener('pageshow', onPageShow);
});

onBeforeUnmount(() => {
  window.removeEventListener('pageshow', onPageShow);
});
</script>
