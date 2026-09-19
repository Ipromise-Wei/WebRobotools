<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { MapSnapshot } from '@/stores/visualization'
const props = defineProps<{ map: MapSnapshot; x: number; y: number; yaw: number }>()
const canvas = ref<HTMLCanvasElement>()
function draw() {
  const el = canvas.value; if (!el) return
  const box = el.getBoundingClientRect(), ratio = devicePixelRatio || 1
  el.width = box.width * ratio; el.height = box.height * ratio
  const ctx = el.getContext('2d'); if (!ctx) return
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.fillStyle = '#081522'; ctx.fillRect(0, 0, box.width, box.height)
  if (!props.map.width || !props.map.data.length) { ctx.fillStyle='#60788c'; ctx.textAlign='center'; ctx.fillText('等待 /map 数据', box.width/2, box.height/2); return }
  const off = document.createElement('canvas'); off.width=props.map.width; off.height=props.map.height
  const oc=off.getContext('2d')!, image=oc.createImageData(off.width, off.height)
  props.map.data.forEach((v,i)=>{ const p=((props.map.height-1-Math.floor(i/props.map.width))*props.map.width+i%props.map.width)*4; const s=v<0?38:230-Math.round(v*2.1); image.data[p]=v<0?24:s; image.data[p+1]=v<0?43:s; image.data[p+2]=v<0?57:s; image.data[p+3]=255 }); oc.putImageData(image,0,0)
  const scale=Math.min(box.width/props.map.width,box.height/props.map.height), w=props.map.width*scale,h=props.map.height*scale, ox=(box.width-w)/2,oy=(box.height-h)/2
  ctx.imageSmoothingEnabled=false; ctx.drawImage(off,ox,oy,w,h)
  const pixel=(p:{x:number;y:number})=>({x:ox+(p.x-props.map.origin_x)/props.map.resolution*scale,y:oy+(props.map.height-(p.y-props.map.origin_y)/props.map.resolution)*scale})
  if(props.map.path.length){ctx.strokeStyle='#65a2ff';ctx.lineWidth=2;ctx.beginPath();props.map.path.forEach((p,i)=>{const q=pixel(p);i?ctx.lineTo(q.x,q.y):ctx.moveTo(q.x,q.y)});ctx.stroke()}
  const robot=pixel({x:props.x,y:props.y});ctx.save();ctx.translate(robot.x,robot.y);ctx.rotate(-props.yaw);ctx.fillStyle='#37d6c0';ctx.beginPath();ctx.moveTo(12,0);ctx.lineTo(-8,-7);ctx.lineTo(-5,0);ctx.lineTo(-8,7);ctx.closePath();ctx.fill();ctx.restore()
}
watch(()=>[props.map.revision,props.x,props.y,props.yaw],()=>nextTick(draw));onMounted(()=>{draw();addEventListener('resize',draw)});onBeforeUnmount(()=>removeEventListener('resize',draw))
</script>
<template><section class="panel map-panel"><div class="section-title"><h2>SLAM 地图与路径</h2><span>{{ map.frame_id }} · {{ map.width }}×{{ map.height }}</span></div><canvas ref="canvas"></canvas><div class="map-legend"><span><i class="robot-color"></i>机器人</span><span><i class="path-color"></i>Nav2 路径</span><small>{{ map.resolution }} m/px</small></div></section></template>
