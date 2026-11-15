<script setup lang="ts">
import { Info, RefreshCw, Download, Search } from 'lucide-vue-next'
import type { Map as LMap, LayerGroup, CircleMarker } from 'leaflet'
const props = defineProps<{ bbox: number[]; period: string; boundary?: any; context?: any }>()
type Event = { id:number; label:string; associations:any[]; latitude:number; longitude:number; bounds:number[]; activity:number; observations:number; scored_observations:number; occurrence_score:number; seasonal_occurrence_score:number|null; activity_score:number|null; local_activity_score:number|null; first_recorded:boolean; no_seasonal_activity:boolean|null; reference_years:number[]; active_reference_years:number[]; prior_observed_years:number; regional_activity_weight:number; support:string; season_sensitive:boolean; reasons:string[]; outlier:boolean; first_detection:string; last_detection:string }
const anchorDate = ref(`${props.period}-15`)
const windowDays = ref(7)
const seasonDays = ref(30)
const reference = ref('viirs')
const threshold = ref(95)
const measure = ref<'occurrence'|'activity'>('occurrence')
const filter = ref('outliers')
const showPoints = ref(false)
const shownRows = ref(20)
const result = shallowRef<any>()
const loading = ref(false)
const error = ref('')
const element = ref<HTMLElement>()
const fmt = (value:any,digits=1) => value == null ? '—' : new Intl.NumberFormat('en-US',{maximumFractionDigits:digits}).format(value)
const score = (event:Event) => measure.value==='occurrence' ? event.occurrence_score : event.activity_score
const visible = computed<Event[]>(() => (result.value?.events || []).filter((event:Event) => filter.value==='all' || (filter.value==='outliers' && event.outlier) || (filter.value==='occurrence' && event.occurrence_score>=threshold.value) || (filter.value==='activity' && event.activity_score!=null && event.activity_score>=threshold.value)).sort((a:Event,b:Event)=>(score(b)??-1)-(score(a)??-1) || b.activity-a.activity))
const colors = ['#e5eadb','#b9c9a0','#ddbb64','#cf7749','#793e67']
const color = (value:number|null) => value == null ? '#92998b' : colors[[75,90,95,99].filter(t=>value>=t).length]!
const explanation = computed(() => measure.value==='occurrence' ? 'Occurrence describes how unusual it is to observe an event here at this time of year. First recorded local activity remains an outlier, regardless of reference support.' : 'Activity compares this event’s own detection count with positive historical single-event windows. Nearby simultaneous events are not added to its count. Missing positive comparisons can leave this score unavailable.')
let map:LMap|undefined
let layers:LayerGroup|undefined
let L:typeof import('leaflet')
let request = 0
let controller:AbortController|undefined
const markers = new Map<number,CircleMarker>()
function textNode(lines:string[]) { const node=document.createElement('div');node.style.whiteSpace='pre-line';node.textContent=lines.join('\n');return node }
function reason(event:Event) { return event.first_recorded ? 'First recorded locally' : event.reasons.includes('rare_occurrence') && event.reasons.includes('unusual_activity') ? 'Occurrence + activity outlier' : event.reasons.includes('rare_occurrence') ? 'Rare occurrence' : event.reasons.includes('unusual_activity') ? 'Unusual activity' : 'Below thresholds' }
function detail(event:Event) {
  return textNode([event.associations.length ? `CAL FIRE overlap: ${event.label} · inferred event ${event.id}` : `Inferred activity event ${event.id}`,
    `${result.value.start_date} – ${result.value.end_date} UTC`,
    `Occurrence: ${fmt(event.occurrence_score,2)} / 100 · Activity: ${fmt(event.activity_score,2)} / 100`,
    reason(event),
    `Own event activity in 10 km comparison area: ${fmt(event.activity)}`,
    `${event.scored_observations} local observations / ${event.observations} across the event window`,
    `Reference: ${event.reference_years.length} years; ${event.active_reference_years.length} active locally`,
    ...(event.first_recorded ? [`No earlier retained observation from another event here; ${event.prior_observed_years} years of preceding archive. This is not proof of no earlier fires.`] : []),
    ...(event.regional_activity_weight ? [`Activity score uses ${fmt(100*event.regional_activity_weight,0)}% regional reference support. Occurrence score is unaffected.`] : []),
    ...(event.support==='limited' ? ['Limited reference support; novelty remains an outlier.'] : []),
    ...(event.season_sensitive ? ['Classification changes with the seasonal reference window.'] : []),
    'Tracking may merge nearby fires or split an event after observation gaps. Circles are comparison areas, not fire perimeters.'])
}
function draw() {
  if(!map||!L)return
  const next=L.layerGroup();markers.clear()
  for(const event of visible.value) {
    const tint=color(score(event))
    const area=L.circle([event.latitude,event.longitude],{radius:10000,color:tint,weight:1,fillColor:tint,fillOpacity:.1})
    area.bindTooltip(()=>detail(event));area.bindPopup(()=>detail(event));next.addLayer(area)
    const marker=L.circleMarker([event.latitude,event.longitude],{radius:event.first_recorded?6:5,color:event.outlier?'#233f36':'#fffef7',weight:1.3,fillColor:tint,fillOpacity:.95})
    marker.bindTooltip(()=>detail(event));marker.bindPopup(()=>detail(event));next.addLayer(marker);markers.set(event.id,marker)
  }
  if(showPoints.value) {
    const lookup=new Map(visible.value.map(event=>[event.id,event]))
    for(const [lat,lon,id] of result.value?.points||[]) {
      const event=lookup.get(id);if(!event)continue
      const dot=L.circleMarker([lat,lon],{radius:2,stroke:false,fillColor:color(score(event)),fillOpacity:.9})
      dot.bindPopup(()=>detail(event));next.addLayer(dot)
    }
  }
  next.addTo(map);layers?.remove();layers=next
}
function focus(event:Event) { map?.setView([event.latitude,event.longitude],9);markers.get(event.id)?.openPopup() }
async function load() {
  const current=++request;controller?.abort();controller=new AbortController()
  loading.value=true;error.value='';result.value=undefined;shownRows.value=20;draw()
  try {
    const next=await $fetch<any>('/api/event-outliers',{signal:controller.signal,query:{anchor_date:anchorDate.value,window_days:windowDays.value,season_days:seasonDays.value,reference:reference.value,threshold:threshold.value,bbox:props.bbox.join(','),include_points:showPoints.value}})
    if(current!==request)return
    result.value=next;draw()
  }catch { if(current===request&&!controller.signal.aborted)error.value='Event scores could not be loaded. Check the date and retry.' }
  finally { if(current===request)loading.value=false }
}
function download() {
  if(!result.value)return
  const blob=new Blob([JSON.stringify(result.value,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a')
  a.href=url;a.download=`charal-event-outliers-${result.value.anchor_date}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
}
watch([anchorDate,windowDays,seasonDays,reference,threshold,showPoints],load)
watch([measure,filter],()=>{shownRows.value=20;draw()})
watch(()=>props.bbox.join(','),()=>{map?.fitBounds([[props.bbox[1]!,props.bbox[0]!],[props.bbox[3]!,props.bbox[2]!]]);load()})
onMounted(async()=>{
  L=await import('leaflet');if(!element.value)return
  map=L.map(element.value,{preferCanvas:true,minZoom:4,maxZoom:13})
  if(props.context)L.geoJSON(props.context,{style:{color:'#a8b4a0',weight:.7,fillColor:'#edf0e4',fillOpacity:.6}}).addTo(map)
  if(props.boundary)L.geoJSON(props.boundary,{style:{color:'#748d66',weight:1.3,fillOpacity:0}}).addTo(map)
  map.attributionControl.addAttribution('NASA FIRMS · US Census Bureau')
  map.fitBounds([[props.bbox[1]!,props.bbox[0]!],[props.bbox[3]!,props.bbox[2]!]])
  await load()
})
onBeforeUnmount(()=>{request++;controller?.abort();map?.remove()})
</script>

<template>
  <section class="panel activity-panel">
    <div class="panel-heading"><div><h2>Unusual events, explained</h2><p>Separate occurrence and activity scores · moving seasonal comparison</p></div><span class="tag">INFERRED EVENTS</span></div>
    <div class="activity-controls">
      <label>Anchor date<input v-model="anchorDate" type="date" min="2001-01-01" max="2025-12-31" aria-label="Event anchor date"></label>
      <label>Measurement window<select v-model.number="windowDays" aria-label="Event measurement window"><option v-for="days in [1,3,7,14]" :key="days" :value="days">{{ days }} day{{days>1?'s':''}} · centered</option></select></label>
      <label>Seasonal comparison<select v-model.number="seasonDays" aria-label="Event seasonal reference"><option v-for="days in [15,30,45,60]" :key="days" :value="days">±{{days}} days · soft weighting</option></select></label>
      <label>Historical reference<select v-model="reference" aria-label="Event historical reference"><option value="viirs">2012–2025 · VIIRS</option><option value="harmonized">2001–2025 · experimental MODIS + VIIRS</option></select></label>
      <label>Threshold<select v-model.number="threshold" aria-label="Event outlier threshold"><option :value="95">Score ≥95</option><option :value="99">Score ≥99</option></select></label>
    </div>
    <p class="activity-explanation">Nearby detections are linked into observed activity events. Each event is compared with equally long historical windows in a fixed 10 km area around its densest observed location. The target event and its measurement years are excluded from the reference.</p>
    <p v-if="reference==='harmonized'" class="activity-notice">Experimental sensor extension: MODIS misses many small detections. Event identities and component scores across the sensor transition have not been independently validated.</p>
    <div v-if="error" class="activity-notice" role="alert">{{error}} <button class="text-button" @click="load">Retry</button></div>
    <p v-if="result?.status==='incomplete_observations'" class="activity-notice" role="status">The complete measurement window is unavailable because of a known sensor gap, startup date or archive boundary. It is not treated as zero activity.</p>
    <div v-if="result?.status==='ok'" class="activity-summary" aria-label="Event outlier summary">
      <div><span>Observed events</span><strong>{{result.events.length}}</strong></div>
      <div><span>Outliers · either component</span><strong>{{result.outlier_events}}</strong></div>
      <div><span>First recorded locally</span><strong>{{result.first_recorded_events}}</strong></div>
      <div><span>Measurement dates · UTC</span><strong class="event-dates">{{result.start_date}}<small> – {{result.end_date}}</small></strong></div>
    </div>
    <p v-if="result?.events_unavailable" class="activity-notice">{{result.events_unavailable}} observed events have insufficient eligible reference years. They have no computed component scores.</p>
    <div class="activity-controls event-view-controls">
      <label>Color and rank by<select v-model="measure" aria-label="Event score component"><option value="occurrence">Unusual occurrence</option><option value="activity">Unusually high activity</option></select></label>
      <label>Show<select v-model="filter" aria-label="Event outlier filter"><option value="outliers">Outliers · either component</option><option value="occurrence">Occurrence outliers</option><option value="activity">Activity outliers</option><option value="all">All observed events</option></select></label>
      <label class="event-points"><input v-model="showPoints" type="checkbox"> Assigned detection points</label>
      <button class="text-button" :disabled="!result||loading" @click="download"><Download :size="14" /> Export events & method</button>
    </div>
    <p class="activity-explanation">{{explanation}}</p>
    <div class="activity-map-wrap"><div ref="element" class="activity-map" aria-label="Observed event outlier map" /><div v-if="loading" class="activity-loading" role="status"><RefreshCw :size="14" class="spin" /> Computing event comparisons…</div></div>
    <div class="activity-legend"><strong>{{measure==='occurrence'?'Occurrence rarity':'Conditional activity rank'}}</strong><span v-for="(label,i) in ['0–75','75–90','90–95','95–99','99–100']" :key="label"><i :style="{background:colors[i]}" />{{label}}</span><span><i style="background:#92998b" /> Unavailable</span></div>
    <p class="activity-explanation">Circles show 10 km comparison areas, not fire perimeters. An event with no earlier recorded local activity remains an occurrence outlier. “First recorded” refers to the selected observation archive; older fires and missed observations remain possible.</p>
    <div v-if="result?.status==='ok'" class="activity-ranking">
      <h3>{{visible.length}} {{filter==='all'?'observed events':'outlier events'}} · {{measure==='occurrence'?'ranked by occurrence':'ranked by activity'}}</h3>
      <p v-if="!visible.length">{{result.events.length?'No events match this filter.':'No retained detections in this measurement window.'}}</p>
      <div v-else class="activity-table-scroll"><table><thead><tr><th>Observed event / CAL FIRE overlap</th><th>Occurrence</th><th>Activity</th><th>Own detections · 10 km</th><th>Reference support</th></tr></thead><tbody><tr v-for="event in visible.slice(0,shownRows)" :key="event.id"><td><button @click="focus(event)"><Search :size="12" />{{event.label}} · #{{event.id}}</button><small class="event-reason">{{reason(event)}}</small></td><td><strong>{{fmt(event.occurrence_score,2)}}</strong></td><td><strong>{{fmt(event.activity_score,2)}}</strong><small v-if="event.regional_activity_weight" class="event-reason">{{fmt(event.regional_activity_weight*100,0)}}% regional support</small></td><td>{{fmt(event.activity)}}<small class="event-reason">{{event.observations}} total observations</small></td><td>{{event.reference_years.length}} years · {{event.active_reference_years.length}} active locally<small class="event-reason">{{event.support==='limited'?'Limited support':'Broader local support'}}{{event.season_sensitive?' · season-sensitive':''}}</small></td></tr></tbody></table></div>
      <button v-if="visible.length>shownRows" class="text-button event-show-more" @click="shownRows+=20">Show more · {{shownRows}} of {{visible.length}}</button>
    </div>
    <div class="panel-note"><Info :size="15" /><span>Reference support never reduces first-occurrence novelty. Activity strength can borrow positive references from equally sized nearby areas; occurrence remains local. These are empirical two-part scores, not probabilities of danger. Tracking and CAL FIRE overlaps are inferred and can merge or split incidents.</span></div>
  </section>
</template>
