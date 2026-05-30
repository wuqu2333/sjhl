import { defineStore } from 'pinia';
import { ref, watch } from 'vue';
import { useIntervalFn, useMediaQuery, useDocumentVisibility } from '@vueuse/core';
import { dashboardApi, type ApiState } from '../api/dashboard';

interface LoadStateOptions {
  silent?: boolean;
  jobsLimit?: number;
}

export const useAppStore = defineStore('app', () => {
  const state = ref<ApiState | null>(null);
  const error = ref('');
  const collapsed = ref(false);
  const lastPollAt = ref(0);
  const pollingPaused = ref(false);

  const isMobile = useMediaQuery('(max-width: 767px)');
  const visibility = useDocumentVisibility();
  let inFlight: Promise<ApiState | null> | null = null;
  let resumeTimer: ReturnType<typeof window.setTimeout> | undefined;

  function normalizeError(err: unknown) {
    return err instanceof Error ? err.message : String(err);
  }

  function pollIntervalMs() {
    return isMobile.value ? 5000 : 2000;
  }

  function defaultJobsLimit() {
    return isMobile.value ? 80 : 200;
  }

  const { pause, resume } = useIntervalFn(() => {
    if (visibility.value !== 'visible' || pollingPaused.value) {
      return;
    }
    const now = Date.now();
    if (now - lastPollAt.value < pollIntervalMs()) {
      return;
    }
    lastPollAt.value = now;
    loadState({ silent: true });
  }, 1000, { immediate: true });

  watch(visibility, (value) => {
    if (value !== 'visible') {
      pollingPaused.value = true;
      pause();
      if (resumeTimer) window.clearTimeout(resumeTimer);
      return;
    }
    if (resumeTimer) window.clearTimeout(resumeTimer);
    resumeTimer = window.setTimeout(() => {
      pollingPaused.value = false;
      resume();
      lastPollAt.value = 0;
      loadState({ silent: true });
    }, isMobile.value ? 1500 : 300);
  });

  async function loadState(options: LoadStateOptions = {}): Promise<ApiState | null> {
    if (options.silent && visibility.value !== 'visible') {
      return state.value;
    }
    if (inFlight) {
      return inFlight;
    }
    inFlight = dashboardApi.state({ jobsLimit: options.jobsLimit || defaultJobsLimit() })
      .then((payload) => {
        state.value = payload;
        lastPollAt.value = Date.now();
        error.value = '';
        return state.value;
      })
      .catch((err) => {
        if (!options.silent) {
          error.value = normalizeError(err);
        }
        return state.value;
      })
      .finally(() => {
        inFlight = null;
      });
    return inFlight;
  }

  async function refreshState(): Promise<ApiState | null> {
    return loadState({ silent: false, jobsLimit: defaultJobsLimit() });
  }

  function scheduleResumeRefresh() {
    if (resumeTimer) window.clearTimeout(resumeTimer);
    resumeTimer = window.setTimeout(() => {
      loadState({ silent: true });
    }, isMobile.value ? 1500 : 300);
  }

  function setCollapsed(value: boolean) {
    collapsed.value = value;
  }

  function clearError() {
    error.value = '';
  }

  function showError(err: unknown) {
    error.value = normalizeError(err);
  }

  return {
    state,
    error,
    collapsed,
    isMobile,
    loadState,
    refreshState,
    scheduleResumeRefresh,
    setCollapsed,
    clearError,
    showError,
    pausePolling: pause,
    resumePolling: resume,
  };
});
