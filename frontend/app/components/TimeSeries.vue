<script setup lang="ts">
const props = withDefaults(defineProps<{
  rows: Record<string, any>[]
  series: { key: string; color: string; label: string; dashed?: boolean }[]
  height?: number
  compact?: boolean
  drawOnScroll?: boolean
  replayKey?: string | number
}>(), { height: 220, compact: false, drawOnScroll: false })
const clipPrefix = useId()
const w = 920
const pad = { left: 52, right: 18, top: 16, bottom: 32 }
const ymax = computed(() => Math.max(1, ...props.rows.flatMap(r => [...props.series.map(s => Number(r[s.key]) || 0), Number(r.upper)||0])) * 1.1)
const x = (i: number) => pad.left + (i / Math.max(1, props.rows.length - 1)) * (w - pad.left - pad.right)
const y = (v: number) => pad.top + (1 - v / ymax.value) * (props.height - pad.top - pad.bottom)
const path = (key: string) => props.rows.map((r, i) => r[key] === null || r[key] === undefined ? '' : `${i === 0 || props.rows[i-1]?.[key] == null ? 'M' : 'L'}${x(i).toFixed(1)},${y(Number(r[key])).toFixed(1)}`).join(' ')
const ticks = computed(() => Array.from({ length: 4 }, (_, i) => ymax.value * i / 3))
const bands = computed(() => {
  const groups: number[][] = []
  let current: number[] = []
  props.rows.forEach((r,i) => {
    if (r.lower != null && r.upper != null) current.push(i)
    else if(current.length){groups.push(current);current=[]}
  })
  if(current.length)groups.push(current)
  return groups.map(g => g.map((i,j)=>`${j?'L':'M'}${x(i)},${y(props.rows[i]!.upper)}`).join(' ')+' '+[...g].reverse().map(i=>`L${x(i)},${y(props.rows[i]!.lower)}`).join(' ')+' Z')
})
const fmt = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : Math.round(n).toString()
</script>

<template>
  <div class="time-series">
    <svg v-chart-motion="!drawOnScroll" v-draw-lines="{enabled:drawOnScroll,replayKey}" :viewBox="`0 0 ${w} ${height}`" role="img" :aria-label="`Time series: ${series.map(s => s.label).join(', ')}`">
      <defs v-if="drawOnScroll">
        <clipPath v-for="(s,index) in series" :id="`${clipPrefix}-line-${index}`" :key="s.key" clipPathUnits="userSpaceOnUse">
          <rect class="chart-line-reveal" :x="pad.left-4" y="0" :width="w-pad.left-pad.right+8" :height="height" />
        </clipPath>
      </defs>
      <g v-for="t in ticks" :key="t">
        <line :x1="pad.left" :x2="w-pad.right" :y1="y(t)" :y2="y(t)" stroke="#e8ebe5" stroke-dasharray="3 5" />
        <text :x="pad.left-12" :y="y(t)+4" text-anchor="end" class="axis-label">{{ fmt(t) }}</text>
      </g>
      <g :clip-path="drawOnScroll ? `url(#${clipPrefix}-line-${series.length-1})` : undefined">
        <path v-for="(band,i) in bands" :key="`band-${i}`" :d="band" fill="#90a87a" opacity=".2" />
      </g>
      <g v-for="(s,index) in series" :key="s.key" :clip-path="drawOnScroll ? `url(#${clipPrefix}-line-${index})` : undefined">
        <path :d="path(s.key)" fill="none" :stroke="s.color" :stroke-width="compact ? 2 : 2.8" :stroke-dasharray="s.dashed ? '5 5' : undefined" stroke-linejoin="round" stroke-linecap="round" />
      </g>
      <template v-for="i in [0, Math.floor(rows.length * .25), Math.floor(rows.length * .5), Math.floor(rows.length * .75), rows.length-1]" :key="i">
        <text v-if="rows[i]" :x="x(i)" :y="height-6" text-anchor="middle" class="axis-label">{{ String(rows[i]?.date || rows[i]?.year || '').slice(0,4) }}</text>
      </template>
    </svg>
    <div class="chart-legend"><span v-for="s in series" :key="s.key"><i :style="{ background: s.color }" />{{ s.label }}</span><span v-if="bands.length"><i style="background:#b8c7a9" />Validation-residual band</span></div>
  </div>
</template>
