<template>
  <a-progress :percent="record.progress?.percent || record.percent || 0" size="small" />
</template>

<script setup lang="ts">
defineProps<{ record: Record<string, any> }>();
</script>
