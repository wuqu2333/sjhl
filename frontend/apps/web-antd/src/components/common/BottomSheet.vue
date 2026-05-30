<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="open" class="sheet-overlay" @click.self="$emit('close')">
        <div class="sheet-panel" :style="{ maxHeight }">
          <div class="sheet-handle" />
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
defineProps<{
  open: boolean;
  maxHeight?: string;
}>();

defineEmits<{
  close: [];
}>();
</script>

<style scoped>
.sheet-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: flex-end;
  -webkit-tap-highlight-color: transparent;
}

.sheet-panel {
  width: 100%;
  max-height: v-bind(maxHeight);
  background: #fff;
  border-radius: 16px 16px 0 0;
  padding: 8px 16px 24px;
  overflow-y: auto;
  box-shadow: 0 -8px 40px rgba(0, 0, 0, 0.12);
}

.sheet-handle {
  width: 36px;
  height: 4px;
  margin: 0 auto 12px;
  border-radius: 2px;
  background: #d1d5db;
}

.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.2s ease;
}
.sheet-enter-active .sheet-panel,
.sheet-leave-active .sheet-panel {
  transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1);
}
.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}
.sheet-enter-from .sheet-panel,
.sheet-leave-to .sheet-panel {
  transform: translateY(100%);
}
</style>
