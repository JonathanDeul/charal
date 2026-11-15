<script setup lang="ts">
const props = defineProps<{ bbox: number[]; period: string; boundary?: any; context?: any }>()
const view = ref('events')
</script>
<template>
  <div class="outlier-view-tabs" aria-label="Outlier comparison unit"><button :class="{active:view==='events'}" :aria-pressed="view==='events'" @click="view='events'">Observed events · two scores</button><button :class="{active:view==='grid'}" :aria-pressed="view==='grid'" @click="view='grid'">Original cell comparison</button></div>
  <FireEventOutliers v-if="view==='events'" v-bind="props" />
  <ActivityGridOutliers v-else v-bind="props" />
</template>
