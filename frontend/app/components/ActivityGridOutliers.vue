<script setup lang="ts">
import { mapDetail } from "~/utils/mapDetail"
import { Info, RefreshCw, Download, Search } from 'lucide-vue-next'
import type { Map as LMap, LayerGroup, Rectangle } from 'leaflet'
const props = defineProps<{ bbox: number[]; period: string; boundary?: any; context?: any }>()
type Cell = { latitude: number; longitude: number; bounds: number[]; score: number; activity: number; typical_activity: number; viirs_reference_score: number | null; reference_sensitive: boolean; outlier: boolean }
const anchorDate = ref(`${props.period}-15`)
const windowDays = ref(7)
const seasonDays = ref(30)
const reference = ref('viirs')
const threshold = ref(95)
const onlyOutliers = ref(false)
const showDetections = ref(false)
const result = shallowRef<any>()
const detections = shallowRef<any>()
const loading = ref(false)
const error = ref('')
const pointError = ref('')
const element = ref<HTMLElement>()
const fmt = (value: any, digits = 1) => value == null ? '—' : new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(value)
const ranked = computed<Cell[]>(() => (result.value?.cells || []).filter((cell: Cell) => cell.activity > 0 && (!onlyOutliers.value || cell.outlier)).sort((a: Cell, b: Cell) => b.score - a.score || b.activity - a.activity))
const unavailable = computed(() => ({
  incomplete_observations: 'The complete measurement window is unavailable: it intersects a listed sensor outage, the archive boundary, or the VIIRS startup period. Choose another date or reference.',
  insufficient_reference: 'Fewer than ten reference years have eligible comparison windows. Expand the seasonal comparison or choose another date.',
  no_grid_coverage: 'This area contains no supported 0.5° cell center. Select a larger area.'
}[result.value?.status as string] || ''))
const benchmark = computed(() => result.value?.diagnostics?.windows?.find((row: any) => row.window_days === windowDays.value))
const colors = ['#e5eadb', '#b9c9a0', '#ddbb64', '#cf7749', '#793e67']
const color = (score: number) => colors[[75, 90, 95, 99].filter(value => score >= value).length]!
let map: LMap | undefined
let layers: LayerGroup | undefined
let L: typeof import('leaflet')
let sequence = 0
let controller: AbortController | undefined
const cellLayers = new Map<string, Rectangle>()
function cellKey(cell: Cell) { return `${cell.latitude},${cell.longitude}` }
function detail(cell: Cell) {
  return mapDetail('Seasonal activity · 0.5° cell', `${result.value.start_date} – ${result.value.end_date} UTC`, [
    ['Activity score', `${fmt(cell.score, 2)} / 100`], ['Activity', `${fmt(cell.activity)} reference-scale detections`],
    ['Historical median', fmt(cell.typical_activity)], ['VIIRS-only score', fmt(cell.viirs_reference_score, 2)],
    ['Reference', `${result.value.reference_years.length} years · seasonal ±${result.value.season_days} days`],
  ], [...(cell.reference_sensitive ? ['Outlier classification changes with reference choice.'] : []),
    'Score describes activity in this cell, not an individual fire or hazard.'])
}
function draw() {
  if (!map || !L) return
  const next = L.layerGroup()
  cellLayers.clear()
  for (const cell of result.value?.cells || []) {
    if (onlyOutliers.value && !cell.outlier) continue
    const b = cell.bounds
    const layer = L.rectangle([[b[1], b[0]], [b[3], b[2]]], { color: '#fffef7', weight: .8, fillColor: color(cell.score), fillOpacity: cell.activity > 0 ? .72 : .15 })
    layer.bindTooltip(() => detail(cell), { className: 'map-detail-tooltip' }); layer.bindPopup(() => detail(cell), { className: 'map-detail-popup', maxWidth: 360 }); next.addLayer(layer)
    cellLayers.set(cellKey(cell), layer)
  }
  if (showDetections.value) for (const row of detections.value?.footprints || []) {
    const [lat, lon] = row
    const cell = result.value?.cells.find((c: Cell) => lat >= c.bounds[1]! && lat < c.bounds[3]! && lon >= c.bounds[0]! && lon < c.bounds[2]!)
    if (!cell || (onlyOutliers.value && !cell.outlier)) continue
    const point = L.circleMarker([lat, lon], { radius: 2.5, stroke: false, fillColor: '#253f38', fillOpacity: .8 })
    point.bindPopup(() => detail(cell), { className: 'map-detail-popup', maxWidth: 360 }); next.addLayer(point)
  }
  next.addTo(map); layers?.remove(); layers = next
}
function focus(cell: Cell) {
  map?.fitBounds([[cell.bounds[1]!, cell.bounds[0]!], [cell.bounds[3]!, cell.bounds[2]!]], { padding: [35, 35], maxZoom: 9 })
  cellLayers.get(cellKey(cell))?.openPopup()
}
async function load() {
  const request = ++sequence
  controller?.abort(); controller = new AbortController()
  const signal = controller.signal
  loading.value = true; error.value = ''; pointError.value = ''
  result.value = undefined; detections.value = undefined; draw()
  try {
    const next = await $fetch<any>('/api/activity-outliers', { signal, query: { anchor_date: anchorDate.value, window_days: windowDays.value, season_days: seasonDays.value, reference: reference.value, threshold: threshold.value, bbox: props.bbox.join(',') } })
    if (request !== sequence) return
    result.value = next; draw()
    if (showDetections.value && next.status === 'ok') {
      try {
        const points = await $fetch<any>('/api/fire-map', { signal, query: { start_date: next.start_date, end_date: next.end_date, bbox: props.bbox.join(','), sensor: next.source === 'modeled_modis' ? 'MODIS' : next.source === 'mixed_transition' ? 'all' : 'VIIRS' } })
        if (request === sequence) { detections.value = points; draw() }
      } catch { if (request === sequence && !signal.aborted) pointError.value = 'Detection overlay unavailable. Activity scores remain available.' }
    }
  } catch { if (request === sequence && !signal.aborted) error.value = 'Activity scores could not be loaded. Check the date and retry.' }
  finally { if (request === sequence) loading.value = false }
}
function download() {
  if (!result.value) return
  const blob = new Blob([JSON.stringify(result.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob), a = document.createElement('a')
  a.href = url; a.download = `charal-seasonal-activity-${result.value.anchor_date}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
}
watch([anchorDate, windowDays, seasonDays, reference, threshold, showDetections], load)
watch(onlyOutliers, draw)
watch(() => props.bbox.join(','), () => { if (map) map.fitBounds([[props.bbox[1]!, props.bbox[0]!], [props.bbox[3]!, props.bbox[2]!]]); load() })
onMounted(async () => {
  L = await import('leaflet')
  if (!element.value) return
  map = L.map(element.value, { preferCanvas: true, minZoom: 4, maxZoom: 12 })
  if (props.context) L.geoJSON(props.context, { style: { color: '#a8b4a0', weight: .7, fillColor: '#edf0e4', fillOpacity: .6 } }).addTo(map)
  if (props.boundary) L.geoJSON(props.boundary, { style: { color: '#748d66', weight: 1.3, fillOpacity: 0 } }).addTo(map)
  map.attributionControl.addAttribution('NASA FIRMS · US Census Bureau')
  map.fitBounds([[props.bbox[1]!, props.bbox[0]!], [props.bbox[3]!, props.bbox[2]!]])
  await load()
})
onBeforeUnmount(() => { sequence++; controller?.abort(); map?.remove() })
</script>

<template>
  <section class="panel activity-panel">
    <div class="panel-heading"><div><h2>Unusual activity, in seasonal context</h2><p>Historical comparison around the same calendar date · no month boundaries</p></div><span class="tag">EXPLORATORY</span></div>
    <div class="activity-controls">
      <label>Event / anchor date<input v-model="anchorDate" type="date" min="2001-01-01" max="2025-12-31" aria-label="Outlier anchor date"></label>
      <label>Measurement window<select v-model.number="windowDays" aria-label="Activity measurement window"><option v-for="days in [1,3,7,14]" :key="days" :value="days">{{ days }} day{{ days > 1 ? 's' : '' }} · centered</option></select></label>
      <label>Seasonal comparison<select v-model.number="seasonDays" aria-label="Seasonal reference window"><option v-for="days in [15,30,45,60]" :key="days" :value="days">±{{ days }} days · soft weighting</option></select></label>
      <label>Historical reference<select v-model="reference" aria-label="Activity historical reference"><option value="viirs">2012–2025 · VIIRS only</option><option value="harmonized">2001–2025 · experimental MODIS + VIIRS</option></select></label>
      <label>Outlier threshold<select v-model.number="threshold" aria-label="Outlier threshold"><option :value="95">Score ≥ 95</option><option :value="99">Score ≥ 99</option></select></label>
    </div>
    <p class="activity-explanation">Compare equally long activity windows near this calendar date in other years. Nearby dates carry more weight; each reference year has equal total weight. All calendar years touched by the measurement window are excluded, including reference windows crossing into them.</p>
    <p class="activity-explanation">VIIRS is the default because short-window MODIS scores disagree substantially in the later-year sensor check. The longer, harmonized reference is available for sensitivity analysis. Select it to explore dates before 2012.</p>
    <p v-if="reference === 'harmonized' && benchmark" class="activity-notice">Experimental sensor extension: the {{ windowDays }}-day benchmark has a mean active-cell score difference of {{ fmt(benchmark.active_score_mae, 1) }} points between MODIS estimates and VIIRS. Historical MODIS ranks can be sensitive to missed small fires.</p>
    <div v-if="error" class="activity-notice" role="alert">{{ error }} <button class="text-button" @click="load">Retry</button></div>
    <div v-if="unavailable" class="activity-notice" role="status">{{ unavailable }}</div>
    <div v-if="result?.summary" class="activity-summary" aria-label="Activity anomaly summary">
      <div><span>Selected-area score</span><strong>{{ fmt(result.summary.score, 2) }}<small> / 100</small></strong></div>
      <div><span>Activity / historical median</span><strong>{{ fmt(result.summary.activity) }}<small> / {{ fmt(result.summary.typical_activity) }}</small></strong></div>
      <div><span>Outlier cells</span><strong>{{ result.outlier_cells }}<small> / {{ result.cells.length }}</small></strong></div>
      <div><span>Reference years</span><strong>{{ result.reference_years.length }}<small> · {{ result.reference_windows }} windows</small></strong></div>
    </div>
    <p v-if="result?.summary" class="activity-explanation">{{ result.start_date }} – {{ result.end_date }} UTC · {{ result.source === 'modeled_modis' ? 'Estimated from MODIS' : result.source === 'mixed_transition' ? 'MODIS / VIIRS transition' : 'Observed VIIRS' }} · {{ fmt(100 * result.modeled_reference_fraction, 0) }}% of reference weight estimated from MODIS. Overlapping windows are correlated; they are not independent events.</p>
    <p v-if="result?.early_platform_caution" class="activity-notice">Early Terra-only MODIS sampling: this estimate extrapolates across the addition of Aqua in 2002.</p>
    <p v-if="result?.summary?.reference_sensitive" class="activity-notice">The selected-area outlier classification changes with the historical reference. VIIRS-only reference score: {{ fmt(result.summary.viirs_reference_score, 2) }}.</p>
    <div class="activity-map-options"><label><input v-model="onlyOutliers" type="checkbox"> Show only outliers</label><label><input v-model="showDetections" type="checkbox"> Overlay detected pixels as points</label><button class="text-button" :disabled="!result || loading" @click="download"><Download :size="14" /> Export scores & method</button></div>
    <div class="activity-map-wrap"><div ref="element" class="activity-map" aria-label="Seasonal activity outlier map" /><div v-if="loading" class="activity-loading" role="status"><RefreshCw :size="14" class="spin" /> Computing seasonal context…</div></div>
    <div class="activity-legend"><strong>Activity percentile</strong><span v-for="(label,i) in ['0–75','75–90','90–95','95–99','99–100']" :key="label"><i :style="{background:colors[i]}" />{{ label }}</span></div>
    <p v-if="pointError" class="activity-notice" role="status">{{ pointError }}</p>
    <p class="activity-explanation">Click a cell or detection for its contextual score. Cells are 0.5° comparison areas, not fire boundaries. A score of 99 means activity exceeds roughly 99% of the weighted reference windows; it is not a probability of danger. Zero activity has score 0.</p>
    <div v-if="result?.status === 'ok'" class="activity-ranking">
      <h3>{{ onlyOutliers ? 'Outlier locations' : 'Highest activity percentiles' }}</h3>
      <p v-if="!ranked.length">{{ onlyOutliers ? 'No cells meet this threshold.' : 'No reported activity in the measurement window.' }}</p>
      <div v-else class="activity-table-scroll"><table><thead><tr><th>Location</th><th>Score</th><th>Activity</th><th>Historical median</th><th>VIIRS-only reference</th></tr></thead><tbody><tr v-for="cell in ranked.slice(0,20)" :key="cellKey(cell)"><td><button @click="focus(cell)"><Search :size="12" />{{ cell.latitude.toFixed(2) }}, {{ cell.longitude.toFixed(2) }}</button></td><td><strong>{{ fmt(cell.score, 2) }}</strong></td><td>{{ fmt(cell.activity) }}</td><td>{{ fmt(cell.typical_activity) }}</td><td>{{ fmt(cell.viirs_reference_score, 2) }}<span v-if="cell.reference_sensitive"> · sensitive</span></td></tr></tbody></table></div>
    </div>
    <div class="panel-note"><Info :size="15" /><span>Daily MODIS calibration is fitted separately from the monthly calendar. Scores remain exploratory: clouds, overpass timing, early platform changes and calibration errors remain. The VIIRS-only column shows sensitivity to reference choice, not a confidence interval.</span></div>
    <details v-if="result?.diagnostics" class="activity-diagnostics"><summary>Check the daily sensor calibration</summary><p>Known benchmark 2021–2025; smooth sensor ratios fitted on 2013–2020. {{ result.diagnostics.note }}</p><p v-for="row in result.diagnostics.windows" :key="row.window_days">{{ row.window_days }} days: cell-window MAE {{ fmt(row.cell_mae, 2) }} · active-window score difference {{ fmt(row.active_score_mae, 1) }} points · outlier agreement {{ fmt(row.active_outlier_agreement * 100, 1) }}% ({{ row.active_comparisons }} comparisons).</p></details>
  </section>
</template>
