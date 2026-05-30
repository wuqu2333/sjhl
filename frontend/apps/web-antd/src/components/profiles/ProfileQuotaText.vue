<template>
  <span>{{ quotaText }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{ used?: number; remaining?: number; total?: number }>();

const quotaText = computed(() => {
  const total = Number(props.total || 0);
  if (total <= 0) return '未知';
  const used = props.used === undefined
    ? Math.max(0, total - Number(props.remaining || 0))
    : Number(props.used || 0);
  return `${formatBytes(used)} / ${formatBytes(total)}`;
});

function formatBytes(value?: number) {
  const size = Number(value || 0);
  return `${(size / 1024 / 1024 / 1024 / 1024).toFixed(2)} TB`;
}
</script>
