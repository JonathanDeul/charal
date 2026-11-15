<script setup lang="ts">
const props = defineProps<{bbox:number[]; period:string; boundary?:any; context?:any}>()
const asOf=ref(`${props.period < '2013-01' ? '2013-01' : props.period}-15`), eventId=ref<number|null>(null), search=ref('')
const events=shallowRef<any[]>([]), result=shallowRef<any>(), busy=ref(false), error=ref('')
let request=0
onBeforeUnmount(()=>{request++})
const visible=computed(()=>events.value.filter(e=>`${e.label} ${e.id}`.toLowerCase().includes(search.value.toLowerCase())))
const colors=['#9c86b6','#d47a4d','#799a65','#ba9a4f','#748ca8']
const series=computed(()=>[{key:'target',color:'#244f3c',label:result.value?.target?.label||'Selected event'},...(result.value?.analogues||[]).map((e:any,i:number)=>({key:`e${i}`,color:colors[i]!,label:`${e.label} · ${e.first_detection.slice(0,4)}`}))])
const rows=computed(()=>Array.from({length:result.value?.age_days||0},(_,i)=>{
  const row:Record<string,any>={date:`D${i+1}`,target:result.value?.target?.cumulative[i]}
  result.value?.analogues?.forEach((e:any,j:number)=>row[`e${j}`]=e.cumulative[i]);return row
}))
function chooseEvent(id:number){eventId.value=id;load(false)}
async function load(list=false){
  const id=++request;busy.value=true;error.value='';result.value=undefined
  try{
    if(list){
      events.value=[]
      const data=await $fetch<any>('/api/compare-fire',{query:{as_of:asOf.value,bbox:props.bbox.join(',')}})
      if(id!==request)return
      events.value=data.events
      if(!events.value.some(e=>e.id===eventId.value))eventId.value=events.value[0]?.id??null
    }
    if(eventId.value!=null){
      const data=await $fetch<any>('/api/compare-fire',{query:{as_of:asOf.value,event_id:eventId.value}})
      if(id===request)result.value=data
    }
  }catch(e:any){if(id===request)error.value=e?.data?.detail||'Fire comparison could not be loaded.'}
  finally{if(id===request)busy.value=false}
}
function download(){
  const url=URL.createObjectURL(new Blob([JSON.stringify(result.value,null,2)],{type:'application/json'}))
  const a=document.createElement('a');a.href=url;a.download=`charal-fire-${eventId.value}-${asOf.value}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
}
watch(()=>[asOf.value,props.bbox.join(',')],()=>load(true),{immediate:true})
</script>
<template>
  <section class="panel comparison-panel" :aria-busy="busy">
    <div class="panel-heading"><div><h2>How does this fire compare with previous ones?</h2><p>Historical replay · observed VIIRS activity · 2013–2025</p></div><button class="text-button" :disabled="!result||busy" @click="download">Export comparison</button></div>
    <div class="activity-controls">
      <label>Historical cutoff · UTC<input v-model="asOf" type="date" min="2013-01-01" max="2025-12-31"></label>
      <label>Filter events · optional<input v-model="search" type="search" placeholder="e.g. Creek"></label>
      
    </div>
    <p class="body-note">Choose a fire on the map or from the list below. The most active event is selected automatically; filtering by name is optional. The map and list show up to 100 VIIRS tracks detected in the selected area during the seven days up to the cutoff. Compare the same number of days since first detection with earlier years, within 300 km and ±60 seasonal days. The global year filter does not restrict this historical reference.</p>
    <p v-if="busy" role="status" class="body-note">Loading historical comparisons…</p>
    <p v-if="error" role="alert" class="body-note">{{error}} <button @click="load(true)">Retry</button></p>
    <p v-if="!busy&&!error&&!events.length" class="body-note">No supported events at this date in the selected area. Choose another date or a wider area.</p>
    <div v-if="events.length" class="event-browser">
      <FireEventPicker :events="visible" :selected="eventId" :bbox="bbox" :boundary="boundary" :context="context" @select="chooseEvent" />
      <div class="event-choice-list" aria-label="Choose a fire">
        <p v-if="!visible.length" class="body-note">No events match this filter. Clear the filter to browse all events at this date.</p>
        <button v-for="e in visible" :key="e.id" class="event-choice" :class="{selected:e.id===eventId}" :aria-pressed="e.id===eventId" :disabled="busy" @click="chooseEvent(e.id)">
          <strong>{{e.label.startsWith('Observed event ')?'Unnamed activity cluster':e.label}}</strong>
          <span>{{e.recent_detections.toLocaleString('en-US')}} detections in the past 7 days</span>
          <small>First detected {{e.first_detection}} · {{e.latitude.toFixed(2)}}°, {{e.longitude.toFixed(2)}}° · track #{{e.id}}</small>
          <span v-if="e.id===eventId">Selected · comparison below</span>
        </button>
      </div>
    </div>
    <p v-if="result?.status==='incomplete_observations'" class="body-note">A known VIIRS gap intersects the selected event's observation period. Its comparison is unavailable; missing observations are not counted as zero.</p>
    <template v-if="result?.status==='ok'">
      <p class="body-note"><strong>{{result.target.label}} · day {{result.age_days}} since first detection ({{result.target.first_detection}}): {{result.target.total.toLocaleString('en-US')}} detections through {{result.as_of}}.</strong></p>
      <p class="body-note">{{result.reference_events}} eligible earlier tracks across {{result.reference_years.length}} years. <template v-if="result.percentile!=null">Activity rank: {{result.percentile.toFixed(1)}}/100 (ties receive half weight).</template><template v-else>No matching earlier tracks; rank unavailable.</template> This is a finite-reference activity rank, not a danger probability.</p>
      <h3>Cumulative detections since first observation · day 1 to {{result.age_days}}</h3>
      <TimeSeries :rows="rows" :series="series" />
      <div v-if="result.analogues.length" class="activity-table-scroll"><table class="comparison-table"><thead><tr><th>Similar earlier track</th><th>First detection</th><th>Distance</th><th>Season offset</th><th>Detections at day {{result.age_days}}</th></tr></thead><tbody><tr v-for="e in result.analogues" :key="e.id"><td>{{e.label}} · #{{e.id}}</td><td>{{e.first_detection}}</td><td>{{e.distance_km}} km</td><td>{{e.season_distance_days}} days</td><td>{{e.total.toLocaleString('en-US')}}</td></tr></tbody></table></div>
      <p class="body-note">{{result.method}}</p><p class="panel-note">{{result.limitations}}</p>
    </template>
  </section>
</template>
