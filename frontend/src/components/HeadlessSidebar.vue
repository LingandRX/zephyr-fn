<script setup>
/**
 * HeadlessSidebar 组件别名，指向 Sidebar.vue
 */
import Sidebar from "./Sidebar.vue";
</script>

<template>
  <Sidebar v-bind="$attrs">
    <template v-for="(_, slot) in $slots" #[slot]="scope">
      <slot :name="slot" v-bind="scope || {}" />
    </template>
  </Sidebar>
</template>
