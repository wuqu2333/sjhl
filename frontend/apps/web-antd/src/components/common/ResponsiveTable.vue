<template>
  <!-- Desktop: a-table -->
  <div class="hidden md:block">
    <a-table
      :columns="columns"
      :data-source="dataSource"
      :row-key="rowKey"
      :loading="loading"
      :size="size"
      :pagination="pagination"
      :scroll="scroll"
    >
      <template v-for="(_, slot) in $slots" #[slot]="scope">
        <slot :name="slot" v-bind="scope || {}" />
      </template>
    </a-table>
  </div>

  <!-- Mobile: card list -->
  <div v-if="dataSource.length" class="block md:hidden space-y-2.5">
    <section
      v-for="record in dataSource"
      :key="(rowKey ? record[rowKey] : undefined) as PropertyKey"
      class="border border-border rounded-lg p-2.5 bg-surface"
      @click="$emit('rowClick', record)"
    >
      <slot name="mobileCard" :record="record" />
    </section>
  </div>
  <a-empty
    v-if="!dataSource.length && !loading"
    class="block md:hidden"
    :description="emptyText"
  />
</template>

<script setup lang="ts" generic="T extends Record<string, unknown>">
defineProps<{
  columns: Array<Record<string, unknown>>;
  dataSource: T[];
  rowKey?: string;
  loading?: boolean;
  size?: 'small' | 'middle' | 'default';
  pagination?: Record<string, unknown> | boolean;
  scroll?: Record<string, unknown>;
  emptyText?: string;
}>();

defineEmits<{
  rowClick: [record: T];
}>();
</script>
