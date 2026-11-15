<script setup lang="ts">
import { Expand, MousePointer2, RotateCcw, Layers, MapPin, Play, Pause, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import type { Map as LMap, LayerGroup, Rectangle, LatLng, Canvas } from 'leaflet'
const props = defineProps<{ bbox: number[]; period: string; sensor: string; boundary?: any; context?: any }>()
const emit = defineEmits<{ select: [bbox: number[]]; reset: [] }>()
const element = ref<HTMLElement>()
const drawing = ref(false)
const anchor = ref<LatLng | null>(null)
const loading = ref(false)
const error = ref('')
const selectionError = ref('')
const total = ref(0)
type Footprint = [number, number, number, number | null, string, number, number, string, number]
type Cell = { bounds: number[]; days: number; first: string; last: string; max_frp: number | null; sources: number; count: number }
type MapData = { footprints: Footprint[]; cells: Cell[]; invalid_geometry: number; total: number }
const data = shallowRef<MapData>()
const displayedFrame = shallowRef<{ label: string; date: string; timeline: boolean }>()
const measure = ref('power')
const geometry = ref('pixels')
const showPoints = ref(false)
const timeline = ref(false)
const playing = ref(false)
const windowDays = ref(1)
const speed = ref(900)
const monthStart = () => `${props.period}-01`
function monthEnd() {
  const [y,m] = props.period.split('-').map(Number)
  return new Date(Date.UTC(y!,m!,0)).toISOString().slice(0,10)
}
const rangeStart = ref(monthStart())
const rangeEnd = ref(monthEnd())
const selectedDate = ref(monthStart())
const utcDay = (value: string) => Date.parse(`${value}T00:00:00Z`) / 86400000
const isoDay = (value: number) => new Date(value * 86400000).toISOString().slice(0,10)
const rangeError = computed(() => {
  const start = utcDay(rangeStart.value), end = utcDay(rangeEnd.value)
  return !Number.isFinite(start) || !Number.isFinite(end) || rangeStart.value < '2001-01-01' || rangeEnd.value > '2025-12-31' || start > end
    ? 'Choose an ordered date range within 2001–2025.' : ''
})
const dayCount = computed(() => rangeError.value ? 0 : utcDay(rangeEnd.value) - utcDay(rangeStart.value))
const dayIndex = computed(() => utcDay(selectedDate.value) - utcDay(rangeStart.value))
const windowStart = computed(() => rangeError.value ? selectedDate.value : isoDay(Math.max(utcDay(rangeStart.value), utcDay(selectedDate.value) - windowDays.value + 1)))
const timeLabel = computed(() => !timeline.value ? new Date(`${props.period}-15T12:00:00`).toLocaleDateString('en-US', { month: 'long', year: 'numeric' }) : windowStart.value === selectedDate.value ? `${selectedDate.value} UTC` : `${windowStart.value} – ${selectedDate.value} UTC`)
let frameTimer: ReturnType<typeof setTimeout> | undefined
type FrameQuery = { year?: string; month?: string; bbox: string; sensor: string; start_date?: string; end_date?: string }
const frameCache = new Map<string, MapData>()
const pendingFrames = new Map<string, { promise: Promise<MapData>; controller: AbortController }>()
let activeKey = ''
let cacheGeneration = 0
function clearFrameCache() {
  cacheGeneration++
  for (const pending of pendingFrames.values()) pending.controller.abort()
  pendingFrames.clear()
  frameCache.clear()
}
function frameQuery(date = selectedDate.value): FrameQuery {
  const [year, month] = props.period.split('-')
  return { year, month, bbox: props.bbox.join(','), sensor: props.sensor,
    ...(timeline.value ? { start_date: isoDay(Math.max(utcDay(rangeStart.value), utcDay(date) - windowDays.value + 1)), end_date: date } : {}) }
}
function fetchFrame(query: FrameQuery): Promise<MapData> {
  const key = JSON.stringify(query)
  const cached = frameCache.get(key)
  if (cached) {
    frameCache.delete(key)
    frameCache.set(key, cached)
    return Promise.resolve(cached)
  }
  const pending = pendingFrames.get(key)
  if (pending && !pending.controller.signal.aborted) return pending.promise
  const controller = new AbortController()
  const revision = cacheGeneration
  const promise = $fetch<MapData>('/api/fire-map', { query, signal: controller.signal }).then(result => {
    if (revision === cacheGeneration) {
      frameCache.set(key, result)
      while (frameCache.size > 8) frameCache.delete(frameCache.keys().next().value!)
    }
    return result
  }).finally(() => {
    if (pendingFrames.get(key)?.promise === promise) pendingFrames.delete(key)
  })
  pendingFrames.set(key, { promise, controller })
  return promise
}
function prefetchNextFrame() {
  if (!timeline.value || rangeError.value || selectedDate.value >= rangeEnd.value) return
  // Keep one frame ahead even while paused, so stepping and starting are immediate.
  void fetchFrame(frameQuery(isoDay(utcDay(selectedDate.value) + 1))).catch(() => {})
}
function pause() {
  playing.value = false
  clearTimeout(frameTimer)
}
function scheduleFrame() {
  clearTimeout(frameTimer)
  if (!playing.value || loading.value || error.value || rangeError.value) return
  if (selectedDate.value >= rangeEnd.value) { pause(); return }
  frameTimer = setTimeout(() => {
    frameTimer = undefined
    selectedDate.value = isoDay(utcDay(selectedDate.value) + 1)
  }, speed.value)
}
function togglePlayback() {
  if (playing.value) { pause(); return }
  if (rangeError.value) return
  timeline.value = true
  if (selectedDate.value >= rangeEnd.value) selectedDate.value = rangeStart.value
  playing.value = true
  if (error.value) loadPoints()
}
function scrub(value: number) {
  pause()
  selectedDate.value = isoDay(utcDay(rangeStart.value) + Math.max(0, Math.min(dayCount.value, value)))
}
watch([playing, speed], scheduleFrame)
watch([rangeStart, rangeEnd], () => {
  pause()
  if (!rangeError.value) selectedDate.value = rangeStart.value
})
watch(timeline, active => {
  pause()
  if (active && ['days', 'combined'].includes(measure.value)) measure.value = 'power'
})
watch(() => [props.period, props.sensor, props.bbox.join(',')], clearFrameCache, { flush: 'sync' })
const powerColors = ['#f3d493','#e9a354','#d86a36','#b43828','#731e28']
const dayColors = ['#d9e4d2','#a9c3a0','#71a283','#377d70','#17524f']
const palette = computed(() => measure.value === 'days' ? dayColors : powerColors)
const bins = computed(() => measure.value === 'days' ? ['1','2–3','4–7','8–15','16+'] : ['0–10','10–50','50–200','200–1k','1k+'])
const gridRequired = computed(() => ['days', 'combined'].includes(measure.value))
const measureNote = computed(() => ({
  power: 'Pixel-integrated fire radiative power (MW), not temperature or fire severity. Grid view uses the maximum reported pixel FRP.',
  days: 'Distinct UTC dates with a detection in each 1 km cell, not continuous burning duration. Repeated overpasses on one date count once.',
  combined: 'Color shows maximum reported pixel FRP; opacity shows detection days (1–31). An exploratory view, not total energy or fire severity.',
  source: 'MODIS and VIIRS remain separate observations. A shared cell means both sensors reported there, not necessarily at the same time.'
}[measure.value]))
function sourceColor(code: number) { return code === 1 ? '#dd7c4c' : code === 2 ? '#7659a8' : '#235e69' }
function valueColor(value: number | null, days = false) {
  if (value == null) return '#92998b'
  const thresholds = days ? [2,4,8,16] : [10,50,200,1000]
  return (days ? dayColors : powerColors)[thresholds.filter(t => value >= t).length]!
}
function detail(lines: string[]) {
  const node = document.createElement('div')
  node.style.whiteSpace = 'pre-line'
  node.textContent = lines.join('\n')
  return node
}
function renderData() {
  if (!points || !map || !data.value) return
  const nextPoints = L.layerGroup()
  const grid = geometry.value === 'grid'
  const source = measure.value === 'source'
  const mw = (value: number | null) => value == null ? 'Unavailable' : `${fmt(value)} MW`
  if (grid) {
    for (const cell of data.value.cells) {
      const color = source ? sourceColor(cell.sources) : valueColor(measure.value === 'days' ? cell.days : cell.max_frp, measure.value === 'days')
      const opacity = measure.value === 'combined' ? .25 + .65 * (cell.days - 1) / 30 : .75
      const b = cell.bounds
      const layer = L.rectangle([[b[1]!,b[0]!],[b[3]!,b[2]!]], { renderer, smoothFactor: 0, stroke: false, fillColor: color, fillOpacity: opacity })
      const lines = ['1 km activity cell · detections assigned by center', `Maximum pixel FRP: ${mw(cell.max_frp)}`, `${cell.days} detection day(s) · ${cell.count} observations`, `First: ${cell.first} · Last: ${cell.last}`, `Sensor: ${cell.sources === 3 ? 'MODIS + VIIRS' : cell.sources === 1 ? 'MODIS' : 'VIIRS'}`, 'Detection dates do not establish continuous burning.']
      layer.bindTooltip(() => detail(lines)); layer.bindPopup(() => detail(lines)); nextPoints.addLayer(layer)
    }
  }
  for (const row of (grid && !showPoints.value ? [] : data.value.footprints)) {
    const [lat,lon,sensor,frp,date,scan,track,time,satellite] = row
    const color = source ? sourceColor(sensor ? 2 : 1) : valueColor(frp)
    const ageOpacity = displayedFrame.value?.timeline ? Math.pow(.55, utcDay(displayedFrame.value.date) - utcDay(date)) : 1
    const lines = [`${sensor ? 'VIIRS' : 'MODIS'} · ${(['Terra','Aqua','Suomi-NPP'][satellite] || 'Unknown satellite')}`, `${date} ${time.slice(0,2)}:${time.slice(2)} UTC`, `Pixel FRP: ${mw(frp)}`, `Scan × track: ${scan} × ${track} km`, 'Approximate pixel footprint, not burned area.']
    if (geometry.value === 'pixels') {
      const dy = track / 111.195 / 2
      const dx = scan / (111.195 * Math.cos(lat * Math.PI / 180)) / 2
      const layer = L.rectangle([[lat-dy,lon-dx],[lat+dy,lon+dx]], { renderer, smoothFactor: 0, stroke: source, color, weight: .5, fillColor: color, fillOpacity: .55 * ageOpacity })
      layer.bindTooltip(() => detail(lines)); layer.bindPopup(() => detail(lines)); nextPoints.addLayer(layer)
    }
    if (showPoints.value || geometry.value === 'points') {
      const dot = L.circleMarker([lat,lon], { renderer, radius: 2.5, color: '#fffef7', weight: .5, fillColor: geometry.value === 'points' ? color : sourceColor(sensor ? 2 : 1), fillOpacity: .95 * ageOpacity })
      dot.bindTooltip(() => detail(lines)); dot.bindPopup(() => detail(lines)); nextPoints.addLayer(dot)
    }
  }
  // Attach the complete replacement before retiring the previous frame. Leaflet's
  // shared canvas redraws both operations together on its next animation frame.
  nextPoints.addTo(map)
  points.remove()
  points = nextPoints
}
let renderQueued = false
function queueRender() {
  if (renderQueued) return
  renderQueued = true
  nextTick(() => { renderQueued = false; renderData() })
}
watch(measure, () => { if (gridRequired.value) geometry.value = 'grid'; queueRender() })
watch([geometry, showPoints], queueRender)
watch(() => [timeline.value, timeline.value ? windowStart.value : '', timeline.value ? selectedDate.value : '', rangeError.value], loadPoints)
let map: LMap | undefined
let points: LayerGroup | undefined
let rectangle: Rectangle | undefined
let L: typeof import('leaflet')
let renderer: Canvas
let generation = 0
const fmt = (n: number) => new Intl.NumberFormat('en-US').format(n)

async function loadPoints() {
  if (!map || !points) return
  clearTimeout(frameTimer)
  const request = ++generation
  error.value = ''
  if (timeline.value && rangeError.value) { loading.value = false; pause(); return }
  const query = frameQuery()
  const key = JSON.stringify(query)
  if (activeKey !== key) pendingFrames.get(activeKey)?.controller.abort()
  activeKey = key
  loading.value = !frameCache.has(key)
  const frame = { label: timeLabel.value, date: selectedDate.value, timeline: timeline.value }
  try {
    const result = await fetchFrame(query)
    if (request !== generation) return
    data.value = result
    displayedFrame.value = frame
    total.value = result.total
    renderData()
    prefetchNextFrame()
  } catch { if (request === generation) { error.value = 'Map observations could not be loaded.'; pause() } }
  finally { if (request === generation) { loading.value = false; scheduleFrame() } }
}

function setDrawing() {
  selectionError.value = ''
  drawing.value = !drawing.value
  anchor.value = null
  if (drawing.value) map?.dragging.disable()
  else map?.dragging.enable()
}
function resetSelection() {
  rectangle?.remove(); drawing.value=false; anchor.value=null; selectionError.value=''
  map?.dragging.enable(); emit('reset')
}
function fitRegion() {
  map?.fitBounds([[props.bbox[1]!, props.bbox[0]!], [props.bbox[3]!, props.bbox[2]!]], { padding: [22,22] })
}
watch(() => props.sensor, () => { pause(); loadPoints() })
watch(() => props.period, () => {
  pause()
  rangeStart.value = monthStart()
  rangeEnd.value = monthEnd()
  selectedDate.value = monthStart()
  if (timeline.value) timeline.value = false
  else loadPoints()
})
watch(() => props.bbox, () => {
  pause()
  rectangle?.remove();rectangle=undefined
  if (L && map && props.bbox.join(',')!=='-124.5,32.5,-114.1,42.1') {
    rectangle=L.rectangle([[props.bbox[1]!,props.bbox[0]!],[props.bbox[3]!,props.bbox[2]!]],{color:'#23554a',fillOpacity:.025,weight:1.5,dashArray:'5 5'}).addTo(map)
  }
  fitRegion(); loadPoints()
}, { deep: true })
onMounted(async () => {
  L = await import('leaflet')
  if (!element.value) return
  map = L.map(element.value, { zoomControl: false, preferCanvas: true, attributionControl: true, minZoom: 4, maxZoom: 13 })
  if (props.context) {
    L.geoJSON(props.context, { filter: f => f.properties.kind==='state', style: { color: '#a8b4a0', weight: .9, fillColor: '#edf0e4', fillOpacity: 1 } }).addTo(map)
    L.geoJSON(props.context, { filter: f => f.properties.kind==='county', style: { color: '#bcc8ad', weight: .55, fillOpacity: 0, opacity: .7 } }).addTo(map)
  }
  if (props.boundary) L.geoJSON(props.boundary, { style: { color: '#748d66', weight: 1.3, opacity: .85, fillOpacity: .08, fillColor: '#a5b98c' } }).addTo(map)
  map.attributionControl.addAttribution('Geography: <a href="https://www.census.gov/geographies/mapping-files.html">US Census Bureau</a>')
  const labels: [string,number,number,string][] = [
    ['OREGON',42.65,-120.9,'state-label'],['NEVADA',39.2,-116.8,'state-label'],['ARIZONA',34.4,-113.8,'state-label'],
    ['San Francisco',37.77,-122.42,'city-label'],['Los Angeles',34.05,-118.24,'city-label'],['San Diego',32.72,-117.16,'city-label'],
    ['Sacramento',38.58,-121.49,'city-label'],['Fresno',36.74,-119.78,'city-label'],['Redding',40.58,-122.39,'city-label']
  ]
  for (const [name,lat,lon,kind] of labels) {
    const node=document.createElement('span');node.textContent=name
    L.marker([lat,lon],{interactive:false,keyboard:false,icon:L.divIcon({className:kind,html:node,iconSize:[100,14],iconAnchor:[-4,6]})}).addTo(map)
  }
  renderer = L.canvas({ padding: .5 })
  points = L.layerGroup().addTo(map)
  L.control.zoom({ position: 'bottomright' }).addTo(map)
  map.on('click', e => {
    if (!drawing.value) return
    if (!anchor.value) { anchor.value = e.latlng; return }
    const a = anchor.value
    const b = e.latlng
    if (Math.abs(a.lng-b.lng) < .05 || Math.abs(a.lat-b.lat) < .05) return
    const bounds=[Math.max(-124.5,Math.min(a.lng,b.lng)), Math.max(32.5,Math.min(a.lat,b.lat)), Math.min(-114.1,Math.max(a.lng,b.lng)), Math.min(42.1,Math.max(a.lat,b.lat))]
    if(bounds[0]!>=bounds[2]! || bounds[1]!>=bounds[3]!) {
      selectionError.value='Select an area inside the prepared California region.';anchor.value=null;return
    }
    selectionError.value='';rectangle?.remove()
    rectangle = L.rectangle([[bounds[1]!,bounds[0]!],[bounds[3]!,bounds[2]!]], { color: '#23554a', fillOpacity: .06, weight: 2, dashArray: '5 5' }).addTo(map!)
    drawing.value = false
    anchor.value = null
    map?.dragging.enable()
    emit('select', bounds)
  })
  fitRegion()
  await loadPoints()
})
onBeforeUnmount(() => { pause(); generation++; clearFrameCache(); map?.remove() })
</script>

<template>
  <div class="fire-map-explorer">
    <div class="fire-map-controls">
      <label>Color by<select v-model="measure" aria-label="Map color measure"><option value="power">Radiative power (FRP)</option><option v-if="!timeline" value="days">Detection days</option><option v-if="!timeline" value="combined">Power + detection days</option><option value="source">Sensor</option></select></label>
      <label>Show<select v-model="geometry" aria-label="Map geometry"><option v-if="!gridRequired" value="pixels">NASA pixel footprints</option><option value="grid">Activity grid · 1 km</option><option v-if="!gridRequired" value="points">Observation points</option></select></label>
      <label>Time<select v-model="timeline" aria-label="Map time mode"><option :value="false">Whole month</option><option :value="true">Daily animation · UTC</option></select></label>
      <label v-if="geometry !== 'points'" class="fire-point-toggle"><input v-model="showPoints" type="checkbox"> Points</label>
    </div>
    <div v-if="timeline" class="fire-timeline">
      <div class="fire-timeline-settings">
        <label>From<input v-model="rangeStart" type="date" min="2001-01-01" max="2025-12-31" aria-label="Animation start date"></label>
        <label>To<input v-model="rangeEnd" type="date" min="2001-01-01" max="2025-12-31" aria-label="Animation end date"></label>
        <label>Window<select v-model.number="windowDays" aria-label="Animation window"><option :value="1">One day</option><option :value="3">Trailing 3 days</option></select></label>
        <label>Speed<select v-model.number="speed" aria-label="Animation speed"><option :value="1600">Slow</option><option :value="900">Normal</option><option :value="400">Fast</option></select></label>
      </div>
      <p v-if="rangeError" role="alert">{{ rangeError }}</p>
      <div v-else class="fire-timeline-player">
        <button :aria-label="playing ? 'Pause animation' : 'Play animation'" :aria-pressed="playing" @click="togglePlayback"><Pause v-if="playing" :size="15" /><Play v-else :size="15" />{{ playing ? 'Pause' : 'Play' }}</button>
        <button aria-label="Previous day" :disabled="dayIndex <= 0" @click="scrub(dayIndex - 1)"><ChevronLeft :size="16" /></button>
        <input type="range" min="0" :max="dayCount" :value="dayIndex" :aria-valuetext="selectedDate + ' UTC'" aria-label="Animation date" @input="scrub(Number(($event.target as HTMLInputElement).value))">
        <button aria-label="Next day" :disabled="dayIndex >= dayCount" @click="scrub(dayIndex + 1)"><ChevronRight :size="16" /></button>
        <output>{{ displayedFrame?.timeline ? displayedFrame.date : selectedDate }} UTC</output>
      </div>
      <small>Daily observations, not a continuous fire front. The 3-day window fades older pixels and points; grid statistics cover the displayed window. The next day loads ahead; the current frame stays visible while buffering.</small>
    </div>
    <p class="fire-measure-note">{{ measureNote }}</p>
    <div class="map-shell">
    <div ref="element" class="map-canvas" aria-label="NASA fire detection pixel footprints and activity cells in California" />
    <div class="map-toolbar">
      <span class="map-period"><MapPin :size="13" /> {{ displayedFrame?.label || timeLabel }}</span>
      <div class="map-actions">
        <button :class="{ active: drawing }" :aria-pressed="drawing" @click="setDrawing"><MousePointer2 :size="14" /> Select area</button>
        <button aria-label="Fit selected region" title="Fit selected region" @click="fitRegion"><Expand :size="15" /></button>
        <button aria-label="Reset to all California" title="Reset region" @click="resetSelection"><RotateCcw :size="15" /></button>
      </div>
    </div>
    <div v-if="drawing" class="map-instruction">{{ selectionError || (anchor ? 'Click the opposite corner to finish your selection.' : 'Click two opposite corners to select an area. Or use the coordinate fields above.') }}</div>
    <div class="map-key fire-map-legend">
      <template v-if="measure === 'source'"><span><i style="background:#dd7c4c" /> MODIS</span><span><i style="background:#7659a8" /> VIIRS</span><span v-if="geometry === 'grid'"><i style="background:#235e69" /> Both</span></template>
      <template v-else><strong>{{ measure === 'days' ? 'Detection days' : 'FRP · MW' }}</strong><span v-for="(color,i) in palette" :key="color"><i :style="{background:color}" />{{ bins[i] }}</span><span v-if="measure !== 'days'"><i style="background:#92998b" /> No FRP</span></template>
      <small v-if="measure === 'combined'">Detection days · opacity <span v-for="d in [1,8,16,24,31]" :key="d"><i :style="{background: '#b43828', opacity: .25 + .65 * (d-1)/30}" />{{ d }}</span></small>
    </div>
    <div class="map-count"><Layers :size="13" /><span v-if="timeline && rangeError">Invalid date range</span><span v-else-if="loading">{{ data ? 'Buffering next frame · current observations remain visible' : 'Loading observations…' }}</span><span v-else-if="error">{{ error }} <button @click="loadPoints">Retry</button></span><span v-else>{{ fmt(total) }} observations · no sampling<span v-if="!total"> · Try another sensor or date</span></span></div>
    </div>
    <div class="fire-map-caption"><span v-if="geometry === 'pixels'">Approximate scan/track footprints, aligned north. Overlaps can appear darker.</span><span v-else-if="geometry === 'grid'">Fixed 1 km equal-area cells; observations assigned by pixel center. These are activity cells, not pixel boundaries.</span><span v-else>Points mark the centers of detected pixels.</span> Neither view measures burned area or continuous fire duration. No detection does not prove no fire; clouds and observation gaps remain. <span v-if="(showPoints && geometry !== 'points') || (geometry === 'points' && measure === 'source')">Point colors: orange MODIS, purple VIIRS.</span><span v-if="data?.invalid_geometry"> {{ fmt(data.invalid_geometry) }} observations lack valid pixel dimensions and are omitted from footprints and points; grid statistics include them.</span></div>
  </div>
</template>
