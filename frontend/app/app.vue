<script setup lang="ts">
import { Flame, Globe2, ArrowUpRight, ArrowDownToLine, ArrowRight, ChevronRight, ChevronDown, CalendarDays, ChartNoAxesCombined, SlidersHorizontal, BookOpen, Sparkles, CircleHelp, Check, X, Info, MapPinned, Activity, MoveUpRight, RefreshCw, Menu, FlaskConical, Download, ExternalLink } from 'lucide-vue-next'

type Section = 'observe' | 'compare' | 'outliers' | 'harmonize' | 'extremes' | 'methods'
const section = ref<Section>('observe')
const catalog = ref<any>(null)
const overview = ref<any>(null)
const extremes = ref<any>(null)
const loading = ref(true)
const error = ref('')
const filterBusy = ref(false)
const mobileNav = ref(false)
const fromYear = ref(2001)
const toYear = ref(2025)
const sensor = ref('VIIRS')
const region = ref('california')
const customBounds = ref([-124.5,32.5,-114.1,42.1])
const showCoordinates = ref(false)
const selectedMonth = ref('2020-09')
const metric = ref('harmonized_count')
const exportMenu = ref(false)
const coordinateError = ref('')
const regionPresets = [
  { id: 'california', name: 'All California', bbox: [-124.5,32.5,-114.1,42.1] },
  { id: 'north', name: 'Northern California', bbox: [-124.5,39,-119.5,42.1] },
  { id: 'sierra', name: 'Sierra Nevada', bbox: [-121.5,35.5,-117,40.5] },
  { id: 'south', name: 'Southern California', bbox: [-121,32.5,-114.1,35.5] }
]
const nav = [
  { id: 'observe', label: 'Fire calendar', icon: CalendarDays, sub: 'Explore the record' },
  { id: 'compare', label: 'Compare a fire', icon: Flame, sub: 'Historical event context' },
  { id: 'outliers', label: 'Seasonal outliers', icon: Activity, sub: 'Activity in context' },
  { id: 'harmonize', label: 'Sensor harmonization', icon: SlidersHorizontal, sub: 'Connect two sensors' },
  { id: 'extremes', label: 'Extreme fires', icon: ChartNoAxesCombined, sub: 'Explore the tail' },
  { id: 'methods', label: 'Science & sources', icon: BookOpen, sub: 'Behind the numbers' }
]
const bbox = computed(() => region.value === 'custom' ? customBounds.value : regionPresets.find(r=>r.id===region.value)!.bbox)
const regionName = computed(() => region.value === 'custom' ? 'Custom area' : regionPresets.find(r=>r.id===region.value)?.name || 'California')
const years = computed(() => Array.from({length: toYear.value-fromYear.value+1},(_,i)=>toYear.value-i))
const allYears = Array.from({length:25},(_,i)=>2001+i)
const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
const monthly = computed<any[]>(() => overview.value?.monthly || [])
const monthIndex = computed(() => new Map(monthly.value.map(r=>[r.date,r])))
const current = computed(() => monthIndex.value.get(selectedMonth.value))
const summary = computed(() => overview.value?.summary || {})
const evalData = computed(() => catalog.value?.harmonization?.evaluation || {})
const harmonization = computed(() => catalog.value?.harmonization || {})
const selectedMethod = computed(() => harmonization.value.model?.label || (evalData.value.selected_method==='ml'?'Boosted-tree model':'Monthly-ratio calibration'))
const modelLabel = (key:string) => ({historical_transfer:'Regional transfer',ml:'Boosted trees',baseline:'Monthly ratio',seasonal:'Seasonal mean'}[key]||key)
const evaluationConclusion = computed(() => {
  const m=evalData.value.metrics
  if(!m)return ''
  const ml=(m[evalData.value.selected_method] || m.ml)?.monthly_mae,baseline=m.baseline?.monthly_mae
  return ml<baseline?'The active method improves statewide monthly error on the known audit years relative to the ratio baseline.':'The ratio calibration has lower monthly error in this comparison. The active method and its selection rule are recorded with the analysis.'
})
const plotMonthly = computed(() => monthly.value.map(r=>({...r,reference:r.viirs_count})))
const maxCalendar = computed(() => Math.max(1,...monthly.value.map(r=>Number(r[metric.value]) || 0)))
const season = computed(() => months.map((name,i)=>({name,value: monthly.value.filter(r=>r.month===i+1 && r.harmonized_count!=null).reduce((s,r)=>s+r.harmonized_count,0)/Math.max(1,monthly.value.filter(r=>r.month===i+1 && r.harmonized_count!=null).length)})))
const seasonMax = computed(()=>Math.max(1,...season.value.map(r=>r.value)))
const peakMonth = computed(()=>season.value.some(r=>r.value>0)?season.value.reduce((a,b)=>a.value>b.value?a:b):{name:'—',value:0})
const monthLabel = computed(()=>new Date(`${selectedMonth.value}-15T12:00:00`).toLocaleDateString('en-US',{month:'long',year:'numeric'}))
const fmt = (n: any, digits=0) => n == null || !Number.isFinite(Number(n)) ? '—' : new Intl.NumberFormat('en-US',{maximumFractionDigits:digits}).format(Number(n))
const short = (n:any) => n == null ? '—' : new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1}).format(Number(n))
function cell(year:number,month:number) { return monthIndex.value.get(`${year}-${String(month).padStart(2,'0')}`) }
function cellColor(value: number|null|undefined) {
  if (value == null) return '#e8eae4'
  if(value===0) return '#f0f2e8'
  const t = Math.log1p(value)/Math.log1p(maxCalendar.value)
  const colors = ['#e8edcf','#d7dfa9','#c1cb79','#aab75c','#d1ac54','#db8745','#c45b31','#8e3c29']
  return colors[Math.min(7,Math.floor(t*8))]
}
let requestNumber = 0
async function refresh() {
  const req = ++requestNumber
  filterBusy.value = true
  error.value=''
  if(fromYear.value>toYear.value) toYear.value=fromYear.value
  try {
    const query={start_year:fromYear.value,end_year:toYear.value,bbox:bbox.value.join(',')}
    const [o,e]=await Promise.all([$fetch<any>('/api/overview',{query}),$fetch<any>('/api/extremes',{query})])
    if(req!==requestNumber)return
    overview.value=o;extremes.value=e
    if(Number(selectedMonth.value.slice(0,4))<fromYear.value || Number(selectedMonth.value.slice(0,4))>toYear.value) selectedMonth.value=`${toYear.value}-09`
  } catch { if(req===requestNumber)error.value='The prepared dataset could not be loaded. Please retry.' }
  finally { if(req===requestNumber){filterBusy.value=false;loading.value=false} }
}
async function initialize() {
  loading.value=true;error.value=''
  try { catalog.value=await $fetch('/api/catalog'); await refresh() }
  catch { error.value='The observatory API is unavailable. Please retry.';loading.value=false }
}
watch([fromYear,toYear,region],()=>{if(catalog.value)refresh()})
function selectBounds(bounds:number[]) { customBounds.value=bounds;region.value='custom';if(catalog.value)refresh() }
function applyCoordinates() {
  const [w,s,e,n]=customBounds.value
  if(!customBounds.value.every(Number.isFinite)||w!>=e!||s!>=n!||w!< -124.5||e!> -114.1||s!<32.5||n!>42.1) { coordinateError.value='Enter west < east and south < north within California’s bounding box.';return }
  coordinateError.value='';region.value='custom';refresh();showCoordinates.value=false
}
const queryString=computed(()=>new URLSearchParams({start_year:String(fromYear.value),end_year:String(toYear.value),bbox:bbox.value.join(',')}).toString())
function download(kind:string) { window.open(`/api/export/${kind}?${queryString.value}`,'_blank','noopener');exportMenu.value=false }
async function downloadPoints() {
  exportMenu.value=false
  try {
    const [year,month]=selectedMonth.value.split('-')
    const data=await $fetch<any>('/api/hotspots',{query:{year,month,bbox:bbox.value.join(','),sensor:sensor.value,limit:10000}})
    const content=['latitude,longitude,sensor,frp_mw,date,selection_total,sample_size,is_sample',...data.points.map((r:any[])=>[...r,data.total,data.shown,data.shown<data.total].join(','))].join('\n')
    const url=URL.createObjectURL(new Blob([content],{type:'text/csv'}));const a=document.createElement('a');a.href=url;a.download=`charal-detections-${selectedMonth.value}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
  } catch {error.value='The observation export could not be generated. Please retry.'}
}
function exportFigure() {
  const svg=document.querySelector('.main-content .time-series svg, .main-content .tail-chart svg') as SVGSVGElement|null
  if(!svg){window.print();return}
  const ns='http://www.w3.org/2000/svg'
  const original=svg.viewBox.baseVal
  const copy=document.createElementNS(ns,'svg')
  copy.setAttribute('xmlns',ns);copy.setAttribute('viewBox',`0 0 ${original.width} ${original.height+112}`)
  const background=document.createElementNS(ns,'rect');background.setAttribute('width','100%');background.setAttribute('height','100%');background.setAttribute('fill','#fffefa');copy.append(background)
  const style=document.createElementNS(ns,'style');style.textContent='.axis-label{font-family:Arial,sans-serif;font-size:10px;fill:#65745d}text{font-family:Arial,sans-serif}';copy.append(style)
  const title=document.createElementNS(ns,'text');title.setAttribute('x','24');title.setAttribute('y','27');title.setAttribute('fill','#264c3b');title.setAttribute('font-size','17');title.textContent=`Charal · ${section.value==='extremes'?'Wildfire-area tail distribution':'Monthly fire activity'}`;copy.append(title)
  const subtitle=document.createElementNS(ns,'text');subtitle.setAttribute('x','24');subtitle.setAttribute('y','47');subtitle.setAttribute('fill','#65745d');subtitle.setAttribute('font-size','10');subtitle.textContent=`${regionName.value} · ${fromYear.value}–${toYear.value} · ${section.value==='extremes'?'CAL FIRE reported perimeter areas; conditional tail probabilities':'NASA FIRMS; VIIRS-reference detection scale'}`;copy.append(subtitle)
  const plot=svg.cloneNode(true) as SVGSVGElement;plot.setAttribute('y','60');plot.setAttribute('width',String(original.width));plot.setAttribute('height',String(original.height));copy.append(plot)
  const legend=document.createElementNS(ns,'text');legend.setAttribute('x','24');legend.setAttribute('y',String(original.height+88));legend.setAttribute('fill','#65745d');legend.setAttribute('font-size','10');legend.textContent=section.value==='extremes'?'Points: perimeter records · orange: power law · purple dashed: lognormal · sand dotted: exponential':'Green: harmonized activity · purple: observed VIIRS · orange: observed MODIS · shading: validation-residual band';copy.append(legend)
  const footer=document.createElementNS(ns,'text');footer.setAttribute('x','24');footer.setAttribute('y',String(original.height+105));footer.setAttribute('fill','#65745d');footer.setAttribute('font-size','9');footer.textContent='Regional research prototype · Known incomplete months excluded · Data and assumptions: see exported analysis JSON';copy.append(footer)
  const blob=new Blob([new XMLSerializer().serializeToString(copy)],{type:'image/svg+xml;charset=utf-8'})
  const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`charal-${section.value}-${fromYear.value}-${toYear.value}.svg`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
}

onMounted(initialize)
</script>

<template>
  <div class="observatory" @keydown.esc="mobileNav=false;exportMenu=false">
    <a class="skip-link" href="#main">Skip to content</a>
    <button v-if="mobileNav" class="mobile-backdrop" aria-label="Close navigation" @click="mobileNav=false" /><aside class="sidebar" :class="{open:mobileNav}">
      <a class="brand" href="#" aria-label="Charal fire observatory home" @click.prevent="section='observe';mobileNav=false">
        <img class="brand-wordmark" src="/charal-wordmark-ch-flame-v2.png" alt="Charal" width="2172" height="724" />
        <span class="sidebar-caption">FIRE OBSERVATORY</span>
      </a>
      <nav aria-label="Main navigation">
        <button v-for="item in nav" :key="item.id" :class="['nav-item',{selected:section===item.id}]" :aria-current="section===item.id?'page':undefined" @click="section=item.id as Section;mobileNav=false">
          <component :is="item.icon" :size="18" stroke-width="1.6" /><span>{{ item.label }}</span><ChevronRight v-if="section===item.id" :size="14" class="nav-arrow" />
        </button>
      </nav>
      
      <div class="sidebar-bottom"><div class="nasa-wordmark">NASA <span>SPACE APPS<br>CHALLENGE 2026</span></div></div>
    </aside>
    <div class="workspace">
      <header class="topbar"><div class="breadcrumb"><button class="mobile-menu icon-button" aria-label="Toggle navigation" @click="mobileNav=!mobileNav"><Menu :size="20" /></button><Globe2 :size="15" /><span>Observatory</span><ChevronRight :size="13" /><strong>California</strong></div></header>
      <main id="main" class="main-content">
        <div class="page-heading"><div><h1>{{ section==='observe'?'Every season leaves a signal.':section==='compare'?'A fire in historical context.':section==='outliers'?'Unusual for this place and season?':section==='harmonize'?'Two sensors. One longer story.':section==='extremes'?'How rare is an extreme fire?':'Good science starts with context.' }}</h1><p>{{ section==='observe'?'Explore a quarter century of fire activity, connected across satellite generations.':section==='compare'?'Compare a selected event with earlier tracks at the same observation age.':section==='outliers'?'Compare activity with a moving seasonal reference across historical years.':section==='harmonize'?'Measure the sensor difference. Test how well a learned calibration can bridge it.':section==='extremes'?'Explore the size distribution of documented wildfires—and test the power-law hypothesis.':'Follow the data, the assumptions, and the limits behind this observatory.' }}</p></div><div v-if="section!=='outliers' && section!=='compare'" class="export-wrap"><button class="button export-button" :disabled="!overview" :aria-expanded="exportMenu" @click="exportMenu=!exportMenu"><ArrowDownToLine :size="16" /> Export <ChevronDown :size="13" /></button><div v-if="exportMenu" class="export-menu"><button @click="download('monthly')">Monthly activity · CSV</button><button @click="download('fires')">Selected fire records · CSV</button><button v-if="section==='observe'" @click="downloadPoints">Map detections · CSV (up to 10k)</button><button @click="exportFigure">Current chart · SVG</button><button @click="download('analysis')">Analysis & provenance · JSON</button></div></div></div>

        <div v-if="loading" class="loading-state"><RefreshCw :size="26" class="spin" /><h2>Connecting the fire record</h2><p>Loading the prepared California observations and scientific analyses.</p></div>
        <div v-else-if="error && !overview" class="error-state" role="alert"><Info :size="24" /><h2>Data temporarily unavailable</h2><p>{{ error }}</p><button class="button primary" @click="initialize">Try again</button></div>
        <template v-else-if="overview">
          <section v-if="section!=='methods'" class="filterbar" :class="{'calendar-filterbar':section==='observe'}" aria-label="Data selection"><div class="filter-field region-filter"><MapPinned :size="16" /><label for="region">Study area</label><select id="region" v-model="region"><option v-for="r in regionPresets" :key="r.id" :value="r.id">{{ r.name }}</option><option value="custom">Custom area</option></select></div><span class="filter-divider" /><div v-if="section!=='outliers' && section!=='compare'" class="filter-field"><CalendarDays :size="16" /><label for="from-year">Period</label><select id="from-year" v-model.number="fromYear"><option v-for="year in allYears" :key="year">{{ year }}</option></select><span class="date-dash">—</span><select v-model.number="toYear" aria-label="End year"><option v-for="year in allYears" :key="year" :disabled="year<fromYear">{{ year }}</option></select></div><div class="filterbar-end"><span v-if="filterBusy" class="updating"><RefreshCw :size="12" class="spin" /> Updating</span><button class="text-button" :aria-expanded="showCoordinates" @click="showCoordinates=!showCoordinates"><SlidersHorizontal :size="14" /> Coordinates</button></div>
            <dl v-if="section==='observe'" class="selection-totals" aria-label="Selection summary">
              <div><dt :title="`Terra + Aqua · ${fromYear}–${toYear}`">MODIS observations</dt><dd>{{ fmt(summary.modis_count) }}</dd></div>
              <div><dt title="Suomi NPP · available overlap">VIIRS observations</dt><dd>{{ fmt(summary.viirs_count) }}</dd></div>
              <div><dt title="CAL FIRE perimeter records">Documented fire records</dt><dd>{{ fmt(summary.fire_count) }}</dd></div>
            </dl>
          </section>
          <div v-if="showCoordinates && section!=='methods'" class="coordinates-panel"><p>Area selection uses {{ harmonization.grid_degrees || .5 }}° cell centers for the harmonized calendar. Fire events use perimeter centroids.</p><div><label v-for="(label,i) in ['West','South','East','North']" :key="label">{{ label }}<input v-model.number="customBounds[i]" type="number" step="0.1" /></label><button class="button primary" @click="applyCoordinates">Apply area</button></div><p v-if="coordinateError" class="error-text" role="alert">{{ coordinateError }}</p></div>
          <p v-if="region!=='california' && section!=='methods'" class="selection-note">Calendar: {{ harmonization.grid_degrees }}° cell-center selection. Map: exact point selection. Fire areas: complete perimeter records selected by centroid. Areas without supported cell centers have no calendar estimate.</p><div v-if="error" class="inline-error" role="alert">{{ error }} <button @click="refresh">Retry</button></div>

          <template v-if="section==='observe'">
            <div class="explore-grid">
              <section class="panel map-panel"><div class="panel-heading"><div><h2>NASA fire detection footprints</h2></div><div class="segmented" aria-label="Map sensor"><button v-for="s in [{id:'all',label:'Both'},{id:'MODIS',label:'MODIS'},{id:'VIIRS',label:'VIIRS'}]" :key="s.id" :class="{active:sensor===s.id}" :aria-pressed="sensor===s.id" @click="sensor=s.id">{{ s.label }}</button></div></div><ClientOnly><FireMap :bbox="bbox" v-model:period="selectedMonth" :sensor="sensor" :boundary="catalog.boundary" :context="catalog.map_context" @select="selectBounds" @reset="region='california'" /></ClientOnly></section>
              <aside class="insight-panel"><div class="eyebrow"><Sparkles :size="14" /> MONTH IN FOCUS</div><h2>{{ monthLabel }}</h2><div class="focus-value">{{ fmt(current?.harmonized_count) }}<span>VIIRS-reference detections</span></div><p>Explore seasonal outliers to compare a dated activity window with nearby calendar dates in other years.</p><p v-if="current?.known_gap" class="quality-notice">Known sensor outage: {{ current.viirs_missing_day_count || current.modis_missing_day_count }} listed dates. This month is excluded from harmonized comparisons.</p><div class="focus-divider" /><div class="focus-row"><span>MODIS observed</span><strong>{{ fmt(current?.modis_count) }}</strong></div><div class="focus-row"><span>VIIRS observed</span><strong>{{ fmt(current?.viirs_count) }}</strong></div><div class="focus-source"><i :class="current?.source==='observed_viirs'?'observed':'estimated'" />{{ current?.source==='observed_viirs'?'Observed VIIRS reference':current?.source==='modeled_modis'?'Estimated from MODIS':current?.source==='no_grid_coverage'?'No calendar cell center in this area':'Known incomplete observation month' }}</div><button class="insight-link" @click="section='outliers'">Explore seasonal outliers <ArrowRight :size="15" /></button><div class="mini-season"><span class="eyebrow">TYPICAL YEAR</span><div class="season-bars"><div v-for="s in season" :key="s.name" :title="`${s.name}: ${fmt(s.value)} mean detections`"><i :style="{height:`${Math.max(3,s.value/seasonMax*64)}px`,background:s.name===peakMonth.name?'#d47a4d':'#b9c6a9'}" /><span>{{ s.name.slice(0,1) }}</span></div></div></div></aside>
            </div>
            <section class="panel calendar-panel"><div class="panel-heading"><div><h2>The burning calendar </h2><p>When did activity peak? Read across a year, or down a season.</p></div><select v-model="metric" aria-label="Calendar measure" class="measure-select"><option value="harmonized_count">Harmonized activity</option><option value="modis_count">MODIS observations</option><option value="viirs_count">VIIRS observations</option></select></div><div class="calendar-scroll"><div class="calendar-grid"><span class="calendar-year-label">YEAR</span><span v-for="m in months" :key="m" class="calendar-month">{{ m }}</span><template v-for="year in years" :key="year"><span class="calendar-year">{{ year }}</span><button v-for="m in 12" :key="`${year}-${m}`" :class="['calendar-cell',{chosen:selectedMonth===`${year}-${String(m).padStart(2,'0')}`,estimated:cell(year,m)?.source!=='observed_viirs'&&metric==='harmonized_count',missing:cell(year,m)?.[metric]==null}]" :style="{background:cellColor(cell(year,m)?.[metric])}" :aria-label="`${months[m-1]} ${year}: ${cell(year,m)?.[metric]==null?'unavailable':fmt(cell(year,m)?.[metric])} ${metric==='harmonized_count'?'reference-scale':'observed'} detections`" :title="`${months[m-1]} ${year} · ${fmt(cell(year,m)?.[metric])}${cell(year,m)?.source==='modeled_modis'?' · model estimate':''}`" :aria-pressed="selectedMonth===`${year}-${String(m).padStart(2,'0')}`" @click="selectedMonth=`${year}-${String(m).padStart(2,'0')}`"><span class="sr-only">{{ fmt(cell(year,m)?.[metric]) }}</span></button></template></div></div><div class="calendar-footer"><span><span class="estimate-key" /> Hatching: modeled history <span class="missing-key" /> Incomplete / unavailable</span><div class="heatmap-key"><span>Less activity</span><i v-for="c in ['#f0f2e8','#d7dfa9','#c1cb79','#aab75c','#d1ac54','#db8745','#c45b31','#8e3c29']" :key="c" :style="{background:c}" /><span>More</span></div></div><div class="panel-note"><Info :size="13" /><span>Logarithmic color scale. Harmonized activity uses observed VIIRS where available and calibrated MODIS estimates for earlier months. Months with known sensor outages are excluded from harmonized activity. No listed outage does not imply cloud-free observations.</span></div></section>
            <YearComparison :bbox="bbox" :start-year="fromYear" :end-year="toYear" />
            <section class="panel trend-panel"><div class="panel-heading"><div><h2>A longer view of activity</h2><p>Monthly observations and the harmonized reference series</p></div><button class="text-button" @click="exportFigure"><Download :size="14" /> Save chart</button></div><TimeSeries :rows="plotMonthly" :series="[{key:'modis_count',color:'#d7a38a',label:'MODIS observed'},{key:'reference',color:'#9c86b6',label:'VIIRS observed'},{key:'harmonized_count',color:'#2d6551',label:'Harmonized activity'}]" /><div class="panel-note">Hotspot counts depend on observation conditions and sensor sensitivity. The harmonized series is a reference-scale estimate, not a count of distinct fires.</div></section>
          </template>

          <template v-else-if="section==='compare'"><FireComparison :bbox="bbox" :period="selectedMonth" :boundary="catalog.boundary" :context="catalog.map_context" /></template>
          <template v-else-if="section==='outliers'"><ClientOnly><ActivityOutliers :bbox="bbox" :period="selectedMonth" :boundary="catalog.boundary" :context="catalog.map_context" /></ClientOnly></template>

          <template v-else-if="section==='harmonize'">
            <div class="science-banner"><div class="banner-symbol"><SlidersHorizontal :size="25" /></div><div><span class="eyebrow">THE CORE CHALLENGE</span><h2>A sensor change should not look like a fire trend.</h2><p>MODIS and VIIRS observe at different resolutions, sensitivities, and overpass times. We compare learned and statistical calibrations of monthly activity on a common grid.</p></div><span class="science-badge">RESEARCH PROTOTYPE</span></div>
            <div class="method-flow"><div><span class="flow-number">01</span><strong>Observe together</strong><p>Pair MODIS and Suomi NPP VIIRS cell-months in the overlapping record.</p></div><ArrowRight :size="20" /><div><span class="flow-number">02</span><strong>Learn the relationship</strong><p>Choose conservative regional calibration using whole-year forward and backward checks.</p></div><ArrowRight :size="20" /><div><span class="flow-number">03</span><strong>Audit transfer</strong><p>Check later periods, regional errors and the earliest reference year. These historical audit years have been inspected.</p></div></div>
            <section class="panel"><div class="panel-heading"><div><h2>The connected record</h2><p>{{ regionName }} · MODIS history mapped to the VIIRS reference scale</p></div><span class="tag green">{{ selectedMethod }}</span></div><TimeSeries :rows="plotMonthly" :height="280" :series="[{key:'modis_count',color:'#dca17b',label:'MODIS observed'},{key:'viirs_count',color:'#9d85b6',label:'VIIRS reference'},{key:'harmonized_count',color:'#265941',label:'Harmonized activity'}]" /></section>
            <section v-if="evalData.monthly_test?.length" class="panel test-series-panel"><div class="panel-heading"><div><h2>Predictions on known audit years</h2><p>Statewide monthly totals · months without listed NASA outages · {{ (evalData.metrics?.historical_transfer || evalData.metrics?.ml)?.n_months }} audit months</p></div></div><TimeSeries :rows="evalData.monthly_test" :series="[{key:'actual',color:'#265941',label:'Observed VIIRS'},{key:evalData.selected_method==='historical_transfer'?'historical_transfer':'ml',color:'#8e79b5',label:evalData.selected_method==='historical_transfer'?'Transfer prediction':'Boosted-tree prediction'},{key:'baseline',color:'#d58b5c',label:'Ratio prediction'}]" /></section><div class="science-columns"><section class="panel evaluation-panel"><div class="panel-heading"><div><h2>Does learning improve calibration?</h2><p>Frozen statewide evaluation · known audit years {{ (evalData.test_years || [2023,2024,2025]).join(', ') }}</p></div><FlaskConical :size="19" /></div><div v-if="evalData.metrics" class="evaluation-table"><div class="evaluation-row evaluation-head"><span>MODEL</span><span>MONTHLY MAE ↓</span><span>RMSE ↓</span></div><div v-for="(v,key) in evalData.metrics" :key="key" class="evaluation-row"><strong>{{ modelLabel(String(key)) }}</strong><span>{{ fmt((v as any).mae ?? (v as any).monthly_mae,1) }}</span><span>{{ fmt((v as any).rmse ?? (v as any).monthly_rmse,1) }}</span></div></div><p class="body-note">MAE is mean absolute error in predicted detections. Lower is better. Research uses whole-year separation. Historical audit years have been inspected and do not establish prospective accuracy.</p><div class="finding"><Info :size="16" /><p>{{ evaluationConclusion }}</p></div></section><section class="panel"><div class="panel-heading"><div><h2>What the model knows</h2><p>Features available on the historical MODIS side</p></div></div><div class="feature-chips"><span>MODIS detections</span><span>Radiative power</span><span>Pixel geometry</span><span>Spatial clusters</span><span>MODIS context</span><span>Month &amp; location</span></div><p class="body-note">The estimate describes a VIIRS-equivalent observation scale. It cannot recover individual undetected fires or remove all cloud and overpass effects.</p><p v-if="harmonization.uncertainty" class="body-note">The empirical 80% residual band covers {{ fmt(harmonization.uncertainty.test_monthly_band_coverage*100) }}% of known audit monthly totals. They are descriptive error bands, not guaranteed probability intervals.</p><p class="body-note">{{ harmonization.interval_description || 'Uncertainty bands summarize calibration residuals. They do not measure all sources of uncertainty in the satellite record.' }}</p><button class="text-button" @click="section='methods'">Read the validation method <ArrowUpRight :size="14" /></button></section></div>
          </template>

          <template v-else-if="section==='extremes'">
            <div class="science-banner extreme-banner"><div class="banner-symbol"><ChartNoAxesCombined :size="25" /></div><div><span class="eyebrow">A QUESTION, NOT AN ASSUMPTION</span><h2>Many small fires. A few very large ones.</h2><p>Does a power law describe the largest documented fires? Fit the tail, quantify uncertainty, and compare alternative explanations.</p></div><span class="science-badge">CAL FIRE PERIMETERS</span></div>
            <section class="metric-grid"><article class="metric-card"><div class="metric-label">Eligible perimeter records</div><strong>{{ fmt(extremes?.n_above_floor) }}</strong><span class="metric-foot">Above reporting floor · selected region</span></article><article class="metric-card"><div class="metric-label">Fitted tail exponent α</div><strong>{{ fmt(extremes?.alpha,2) }}</strong><span class="metric-foot">{{ extremes?.alpha_ci ? `Empirical 95% interval: ${fmt((extremes.alpha_empirical_ci||extremes.alpha_ci)[0],2)}–${fmt((extremes.alpha_empirical_ci||extremes.alpha_ci)[1],2)}` : 'Bootstrap interval not available for this selection' }}</span></article><article class="metric-card"><div class="metric-label">Tail starts at xₘᵢₙ</div><strong>{{ fmt(extremes?.xmin) }}<span class="metric-small"> ha</span></strong><span class="metric-foot">{{ fmt(extremes?.tail_n) }} records in fitted tail</span></article><article class="metric-card"><div class="metric-label">Goodness-of-fit p</div><strong>{{ fmt(extremes?.p_value,3) }}</strong><span class="metric-foot">{{ extremes?.p_value==null?'Bootstrap not run for this selection':'Bootstrap compatibility test' }}</span></article></section>
            <section class="panel"><div class="panel-heading"><div><h2>The distribution of large fires</h2><p>Tail probability conditional on area ≥ xₘᵢₙ · {{ regionName }} · {{ fromYear }}–{{ toYear }}</p></div><button class="text-button" @click="exportFigure"><Download :size="14" /> Save chart</button></div><TailChart v-if="extremes?.ccdf?.length" :result="extremes" /><div v-else class="empty-state"><ChartNoAxesCombined :size="28" /><h3>Too few events to fit a tail</h3><p>Choose a larger region or a longer period. Reliable tail fitting needs sufficient large-fire observations.</p></div><div class="panel-note"><Info :size="14" /><span>Event areas come from mapped perimeters, not hotspot pixel counts. The fit excludes smaller events below a reporting floor of at least 300 acres (121.4 ha).</span></div></section>
            <div class="science-columns"><section class="panel"><div class="panel-heading"><div><h2>What does the evidence say?</h2><p>Alternative distributions matter</p></div></div><p class="body-note">{{ extremes?.interpretation || extremes?.conclusion || 'A straight line on a logarithmic plot is a starting point. Statistical tests assess whether a power-law tail is plausible and whether alternative tails explain the data better.' }}</p><div v-for="key in ['lognormal_comparison','exponential_comparison']" :key="key" class="comparison-row"><span>Power law vs {{ key.split('_')[0] }}</span><strong>{{ String(extremes?.[key]?.favored || extremes?.[key]?.preferred || 'See exported diagnostics').replaceAll('_',' ') }}</strong></div><p class="body-note">{{ extremes?.comparison_description || 'Comparisons use the same events above the fitted threshold. Data truncation, suppression, climate, and mixed fire regimes can all affect the observed tail.' }}</p></section><section class="panel next-question"><div class="panel-heading"><div><h2>From statistics to mechanisms</h2><p>The Drossel–Schwabl connection</p></div><Flame :size="20" /></div><p class="body-note">Growth, ignition, and connected vegetation can generate fires across many scales in a simple cellular model. That makes it a useful experiment for asking how collective fire patterns emerge.</p><p class="body-note">This PoC tests empirical size distributions first. A future simulation can explore how both landscape dynamics and satellite sampling reshape those distributions.</p><span class="roadmap-label">SIMULATION · FUTURE EXPERIMENT</span></section></div>
          </template>

          <template v-else>
            <div class="methods-layout"><div><section class="panel prose-panel"><span class="eyebrow">01 / PURPOSE</span><h2>One continuous view of observed fire activity</h2><p>Charal is a regional proof of concept for the NASA Space Apps 2026 challenge, Harmonization of MODIS and VIIRS Hot Spots. It connects a historical satellite record, tests a learned sensor calibration, and investigates extreme fire sizes in California.</p><p>The calendar’s common unit is monthly activity on a VIIRS-reference observation scale. Observed MODIS and VIIRS detections remain available separately. A fixed Suomi NPP reference avoids increasing activity simply by adding more VIIRS platforms.</p><span class="eyebrow">02 / DATA</span><h2>NASA observations, independently documented events</h2><p>NASA FIRMS provides MODIS (Terra and Aqua) and VIIRS 375 m (Suomi NPP) historical active-fire detections. MODIS archive version fields vary across years; this snapshot is not a uniform processing collection. CAL FIRE FRAP provides mapped historical wildfire perimeters. The prepared snapshot ends in 2025.</p><p>Thermal detections describe pixels containing one or more thermal anomalies. They do not give the exact fire footprint or a count of distinct fires. Missing detections can result from clouds, smoke, canopy, sensor gaps, or fire activity between overpasses.</p><p>Historical perimeters are also incomplete. Reporting thresholds differ by vegetation and agency; complex fires may overlap their component records. The tail analysis applies a documented minimum size and records its cleaning decisions.</p><span class="eyebrow">03 / HARMONIZATION</span><h2>Calibration that can be checked</h2><p>We aggregate onto a common {{ harmonization.grid_degrees || .5 }}° grid by month, pair the overlapping MODIS and VIIRS record, and compare a learned model with simpler baselines. Entire years are held out; a separate spatial check tests geographic transfer. The active regional mixture uses forward and backward checks within the training years. Later historical periods are known audits, not an untouched test.</p><p>Known missing-date flags from FIRMS exclude incomplete sensor-months from fitting and the harmonized calendar. January 2012 predates full-month VIIRS coverage and uses a MODIS estimate. No listed outage establishes complete observation exposure. Terra alone supplies the early MODIS record; Aqua begins in July 2002. Early backcasts therefore also extrapolate across a platform-sampling change. Earlier activity is an estimated observation-scale equivalent. The active method retains the seasonal calibration north of 39.5°N and uses a conditional-count learner to the south, as selected by training-period transfer checks. Before July 2002 it retains the original baseline and flags the unsupported Terra-only regime. Small fires missed by MODIS are not reconstructed as new geographic detections. Empirical aggregate residual bands and separate year-block bootstrap ranges describe only part of the uncertainty; complete cloud and observation-opportunity information is not present in the hotspot CSVs.</p><span class="eyebrow">04 / EXTREMES</span><h2>Test the power law</h2><p>Fire area is measured in hectares from the reported CAL FIRE perimeter area. Above a minimum reporting floor, a maximum-likelihood Pareto tail is fitted with an estimated lower threshold. Bootstrap goodness-of-fit and parameter intervals are reported where available, alongside lognormal and exponential comparisons on the same tail.</p><p>A high goodness-of-fit p-value does not prove a power law. A power-law fit also does not establish self-organized criticality. Drossel–Schwabl is a possible future explanatory experiment, with known limitations in its scaling behavior.</p><span class="eyebrow">05 / REPRODUCIBILITY</span><h2>A transparent research prototype</h2><p>Data acquisition, model fitting, held-out metrics, statistical tests, and provenance are reproducible from scripts in the project. Exported analysis includes the active selection and source information. Results support exploration of historical patterns, not operational emergency decisions.</p><button class="button" @click="download('analysis')"><Download :size="16" /> Download analysis & provenance</button></section></div><aside><section class="panel source-panel"><span class="eyebrow">PRIMARY SOURCES</span><a href="https://firms.modaps.eosdis.nasa.gov/download/" target="_blank" rel="noopener"><span><strong>NASA FIRMS</strong><small>Historical active-fire data</small></span><ArrowUpRight :size="17" /></a><a href="https://data.ca.gov/@cal-fire/california-fire-perimeters-all" target="_blank" rel="noopener"><span><strong>CAL FIRE FRAP</strong><small>Historical wildfire perimeters</small></span><ArrowUpRight :size="17" /></a><a href="https://epubs.siam.org/doi/10.1137/070710111" target="_blank" rel="noopener"><span><strong>Clauset et al., 2009</strong><small>Testing empirical power laws</small></span><ArrowUpRight :size="17" /></a><a href="https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.69.1629" target="_blank" rel="noopener"><span><strong>Drossel & Schwabl, 1992</strong><small>Forest-fire model</small></span><ArrowUpRight :size="17" /></a><a href="https://journals.aps.org/pre/abstract/10.1103/PhysRevE.70.066707" target="_blank" rel="noopener"><span><strong>Pruessner & Jensen, 2004</strong><small>Limits of simple scaling</small></span><ArrowUpRight :size="17" /></a></section><div class="methods-note"><FlaskConical :size="22" /><h3>Built for exploration</h3><p>Regional coverage. Frozen historical snapshot. Explicit assumptions. No live warning or spread forecast.</p></div></aside></div>
          </template>
          <footer class="page-footer"><span><span class="footer-dot" /> NASA FIRMS × CAL FIRE FRAP <span class="dot-sep">·</span> Historical snapshot 2001–2025</span><span>Charal <span class="dot-sep">/</span> NASA Space Apps 2026</span></footer>
        </template>
      </main>
    </div>
  </div>
</template>
