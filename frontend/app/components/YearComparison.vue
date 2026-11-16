<script setup lang="ts">
const props = defineProps<{ bbox:number[]; startYear:number; endYear:number }>()
const reference = ref('viirs'), order = ref('rank')
const first = ref(2020), second = ref(2021)
const chartReplay = ref(0)
function selectYear(year: number) { first.value = year; chartReplay.value++ }
const result = shallowRef<any>(), error = ref(''), busy = ref(false)
let request = 0
onBeforeUnmount(()=>{request++})
const years = computed<any[]>(()=>(result.value?.years || []).filter((r:any)=>reference.value!=='viirs'||r.year>=2013))
const sorted = computed(()=>[...years.value].sort((a,b)=>order.value==='year'?b.year-a.year:(a.rank??999)-(b.rank??999)||b.year-a.year))
const maximum = computed(()=>Math.max(1,...years.value.map(r=>r.total||0)))
const a = computed(()=>years.value.find(r=>r.year===first.value))
const b = computed(()=>years.value.find(r=>r.year===second.value))
const rows = computed(()=>['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].map((date,i)=>({date,a:a.value?.monthly[i]??null,b:b.value?.monthly[i]??null})))
const fmt = (n:any)=>n==null?'Unavailable':new Intl.NumberFormat('en-US',{maximumFractionDigits:0}).format(n)
const insight = computed(()=>{
  if(!a.value?.complete||!b.value?.complete)return 'Choose two complete years for an annual percentage comparison. Monthly gaps remain visible below.'
  if(!b.value.total)return 'The comparison year has zero reported detections; a percentage difference is undefined.'
  const change=100*(a.value.total/b.value.total-1)
  return `${first.value} recorded ${Math.abs(change).toFixed(1)}% ${change>=0?'more':'fewer'} detections than ${second.value} in the selected area.`
})
async function load(){
  const id=++request;busy.value=true;error.value=''
  try {
    const data=await $fetch<any>('/api/compare-years',{query:{bbox:props.bbox.join(','),start_year:props.startYear,end_year:props.endYear,reference:reference.value}})
    if(id!==request)return
    result.value=data
    const available=years.value.map((r:any)=>r.year)
    if(available.length && !available.includes(first.value))first.value=available.at(-1)
    if(available.length && !available.includes(second.value))second.value=available.at(-2)??available[0]
  }catch(e:any){if(id===request){error.value=e?.statusCode===404?'The running service does not support year comparisons yet.':'Year comparison could not be loaded.';result.value=undefined}}
  finally{if(id===request)busy.value=false}
}
function download(){
  const url=URL.createObjectURL(new Blob([JSON.stringify(result.value,null,2)],{type:'application/json'}))
  const a=document.createElement('a');a.href=url;a.download='charal-year-comparison.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
}
watch(()=>[props.bbox.join(','),props.startYear,props.endYear,reference.value],load,{immediate:true})
</script>
<template>
  <section class="panel comparison-panel" aria-label="Compare years" :aria-busy="busy">
    <div class="panel-heading"><div><h2>Which years had more burning activity?</h2><p>Compare years · satellite activity in the selected area · through 2025</p></div><button class="text-button" :disabled="!result||busy" @click="download">Export comparison</button></div>
    <div class="activity-controls">
      <label>Observation reference<select v-model="reference"><option value="viirs">Observed VIIRS · complete years from 2013</option><option value="harmonized">Harmonized · modeled history from 2001</option></select></label>
      <label>Sort years<select v-model="order"><option value="rank">Most activity first</option><option value="year">Newest first</option></select></label>
      <label>Compare year<select v-model.number="first"><option v-for="r in years" :key="r.year" :value="r.year">{{r.year}}</option></select></label>
      <label>With year<select v-model.number="second"><option v-for="r in years" :key="r.year" :value="r.year">{{r.year}}</option></select></label>
    </div>
    <p v-if="busy" role="status" class="body-note">Loading year comparison…</p>
    <p v-if="error" role="alert" class="body-note">{{error}} <button @click="load">Retry</button></p>
    <template v-if="result && !busy">
      <p v-if="!years.length" class="body-note">No supported VIIRS years in this display period. Include years from 2013 onward or choose the harmonized reference.</p>
      <p class="body-note"><strong>{{insight}}</strong></p>
      <div class="comparison-columns">
        <TransitionGroup v-stagger-motion="'bars'" name="year-ranking" tag="div" class="year-bars" aria-label="Annual detection ranking">
          <button v-for="r in sorted" :key="r.year" class="year-bar" :aria-label="`${r.year}: ${fmt(r.total)} detections, ${r.available_months}/12 eligible months`" @click="selectYear(r.year)">
            <span>{{r.year}}<small>{{r.rank?`#${r.rank}`:'Unranked'}}</small></span>
            <span class="bar-track"><i v-if="r.complete" :style="{width:`${r.total/maximum*100}%`}" /></span>
            <span>{{fmt(r.total)}}<small>{{r.available_months}}/12 months{{r.modeled?' · modeled':''}}</small></span>
          </button>
        </TransitionGroup>
        <div><h3>Monthly activity · {{first}} and {{second}}</h3><TimeSeries draw-on-scroll :replay-key="`${first}:${second}:${chartReplay}`" :rows="rows" :series="[{key:'a',color:'#2d6551',label:String(first)},{key:'b',color:'#9c86b6',label:String(second)}]" /><p class="body-note">{{result.eligible_years}} complete years ranked. Click a year to compare its seasonal pattern.</p></div>
      </div>
      <p class="panel-note">{{result.method}} Detections are neither distinct fires nor burned area. Harmonization is an empirical observation-scale estimate; sensor changes and observation conditions still affect comparisons.</p>
    </template>
  </section>
</template>
