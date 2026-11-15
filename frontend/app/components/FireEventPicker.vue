<script setup lang="ts">
import type { Map as LMap, LayerGroup } from 'leaflet'
const props=defineProps<{events:any[]; selected:number|null; bbox:number[]; boundary?:any; context?:any}>()
const emit=defineEmits<{select:[id:number]}>()
const element=ref<HTMLElement>()
let map:LMap|undefined, layers:LayerGroup|undefined, L:typeof import('leaflet')|undefined
let disposed=false
function fit(){map?.fitBounds([[props.bbox[1]!,props.bbox[0]!],[props.bbox[3]!,props.bbox[2]!]])}
function draw(){
  if(!L||!map)return
  layers?.remove();layers=L.layerGroup()
  for(const event of props.events){
    const selected=event.id===props.selected
    const marker=L.circleMarker([event.latitude,event.longitude],{radius:selected?10:Math.min(8,4+Math.log10(event.recent_detections+1)),color:selected?'#213f30':'#fff',weight:2,fillColor:selected?'#d47a4d':'#52765b',fillOpacity:.9})
    const text=document.createElement('span')
    text.textContent=`${event.label} · ${event.recent_detections.toLocaleString('en-US')} recent detections · click to compare`
    marker.bindTooltip(text);marker.on('click',()=>emit('select',event.id));layers.addLayer(marker)
  }
  layers.addTo(map)
}
watch(()=>[props.events,props.selected],draw)
watch(()=>props.bbox.join(','),fit)
onMounted(async()=>{
  L=await import('leaflet')
  if(disposed||!element.value)return
  map=L.map(element.value,{preferCanvas:true,minZoom:4,maxZoom:13})
  if(props.context)L.geoJSON(props.context,{style:{color:'#a8b4a0',weight:.7,fillColor:'#edf0e4',fillOpacity:.6}}).addTo(map)
  if(props.boundary)L.geoJSON(props.boundary,{style:{color:'#748d66',weight:1.3,fillOpacity:0}}).addTo(map)
  map.attributionControl.addAttribution('NASA FIRMS · US Census Bureau')
  fit();draw()
})
onBeforeUnmount(()=>{disposed=true;map?.remove()})
</script>
<template><div class="event-choice-map"><div ref="element" class="event-picker-map" aria-label="Click an observed fire to compare it" /><p class="body-note">Orange: selected event. Markers locate recent detections; they are not fire perimeters. The list provides keyboard-accessible selection.</p></div></template>
