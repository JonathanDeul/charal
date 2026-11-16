<script setup lang="ts">
defineProps<{ open: boolean }>()
</script>

<template>
  <div class="motion-collapse" :class="{ 'is-open': open }" :inert="!open" :aria-hidden="!open">
    <div class="motion-collapse-inner"><slot /></div>
  </div>
</template>
