<script setup lang="ts">
const props = defineProps<{ result: any }>()
const width = 820, height = 360
const pad = { l: 64, r: 30, t: 24, b: 54 }
const rows = computed(() => props.result?.ccdf || [])
const extent = computed(() => {
  const xs = rows.value.map((r: any) => Number(r.area_ha)).filter((v: number) => v > 0)
  return { min: Math.log10(Math.min(...xs, 100)), max: Math.log10(Math.max(...xs, 1000)), ymin: Math.log10(Math.max(1e-5,Math.min(...rows.value.map((r:any)=>r.empirical).filter((v:number)=>v>0),.01))) }
})
const x = (v: number) => pad.l + (Math.log10(v)-extent.value.min)/(extent.value.max-extent.value.min)*(width-pad.l-pad.r)
const y = (v: number) => pad.t + Math.log10(Math.max(v,1e-8))/extent.value.ymin*(height-pad.t-pad.b)
const curve = (key: string) => rows.value.filter((r: any) => r[key] > 0 && r.area_ha >= (props.result?.xmin || 0)).map((r: any,i: number)=>`${i?'L':'M'}${x(r.area_ha).toFixed(2)},${y(r[key]).toFixed(2)}`).join(' ')
const xticks = computed(() => Array.from({length: Math.ceil(extent.value.max)-Math.floor(extent.value.min)+1},(_,i)=>10**(Math.floor(extent.value.min)+i)).filter(v=>Math.log10(v)>=extent.value.min && Math.log10(v)<=extent.value.max))
const yticks = computed(() => [1,.1,.01,.001,.0001].filter(v=>Math.log10(v)>=extent.value.ymin))
</script>

<template>
  <div class="tail-chart">
    <svg v-chart-motion :viewBox="`0 0 ${width} ${height}`" role="img" aria-label="Log-log complementary cumulative distribution of fire areas, with fitted power-law, lognormal and exponential tails">
      <defs><clipPath id="tail-clip"><rect :x="pad.l" :y="pad.t" :width="width-pad.l-pad.r" :height="height-pad.t-pad.b" /></clipPath></defs>
      <g v-for="v in yticks" :key="v"><line :x1="pad.l" :x2="width-pad.r" :y1="y(v)" :y2="y(v)" stroke="#e3e8df" stroke-dasharray="3 5" /><text :x="pad.l-12" :y="y(v)+4" text-anchor="end" class="axis-label">{{ v >= .01 ? v : v.toExponential(0) }}</text></g>
      <g v-for="v in xticks" :key="v"><line :x1="x(v)" :x2="x(v)" :y1="pad.t" :y2="height-pad.b" stroke="#edf0e9" /><text :x="x(v)" :y="height-pad.b+22" text-anchor="middle" class="axis-label">{{ v >= 1000 ? `${v/1000}k` : v }}</text></g>
      <g clip-path="url(#tail-clip)">
        <line v-if="result?.xmin" :x1="x(result.xmin)" :x2="x(result.xmin)" :y1="pad.t" :y2="height-pad.b" stroke="#a8b3a4" stroke-dasharray="4 5" />
        <path :d="curve('lognormal')" fill="none" stroke="#8e79b5" stroke-width="2" stroke-dasharray="5 5" />
        <path :d="curve('exponential')" fill="none" stroke="#c3a66b" stroke-width="2" stroke-dasharray="3 5" />
        <path :d="curve('power_law')" fill="none" stroke="#d97746" stroke-width="2.8" />
        <circle v-for="(r,i) in rows" :key="i" :cx="x(r.area_ha)" :cy="y(r.empirical)" r="2.8" fill="#284d41" opacity=".72" />
      </g>
      <text :x="width/2" :y="height-6" text-anchor="middle" class="axis-label">Fire area (hectares) · logarithmic scale</text>
      <text :transform="`translate(16,${height/2}) rotate(-90)`" text-anchor="middle" class="axis-label">P(area ≥ x | area ≥ xₘᵢₙ) · log scale</text>
    </svg>
    <div class="chart-legend"><span><i style="background:#284d41" />Perimeter records</span><span><i style="background:#d97746" />Power law</span><span><i style="background:#8e79b5" />Lognormal</span><span><i style="background:#c3a66b" />Exponential</span></div>
  </div>
</template>
