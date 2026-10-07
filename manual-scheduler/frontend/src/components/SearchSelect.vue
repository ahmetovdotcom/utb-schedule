<script setup>
import { computed, ref, useId } from 'vue'
const props = defineProps({ modelValue: [Number, String], options: {type:Array,default:()=>[]}, label: String, placeholder: String })
const emit = defineEmits(['update:modelValue'])
const id = useId(), opened = ref(false), query = ref(''), active = ref(0)
const normalize = text => String(text||'').toLocaleLowerCase('ru').replaceAll('ё','е').trim()
const matches = computed(()=>{
  const words = normalize(query.value).split(/\s+/).filter(Boolean)
  return props.options.filter(option=>words.every(word=>normalize(`${option.name} ${option.department||''}`).includes(word)))
})
const visible = computed(()=>matches.value.slice(0,60))
const selected = computed(()=>props.options.find(option=>option.id===props.modelValue))
function open(){opened.value=true;query.value='';active.value=0}
function input(event){query.value=event.target.value;active.value=0;opened.value=true;emit('update:modelValue','')}
function choose(option){if(!option)return;emit('update:modelValue',option.id);opened.value=false;query.value=''}
function move(delta){if(!opened.value)open();else active.value=Math.max(0,Math.min(visible.value.length-1,active.value+delta))}
function close(event){if(!event.currentTarget.contains(event.relatedTarget))opened.value=false}
</script>
<template>
  <div class="search-select" @focusout="close">
    <label :for="id">{{label}}</label>
    <div class="search-control"><input :id="id" role="combobox" autocomplete="off" :placeholder="placeholder||'Начните вводить…'" :value="opened?query:(selected?.name||'')" :aria-expanded="opened" :aria-controls="id+'-list'" aria-autocomplete="list" :aria-activedescendant="opened&&visible[active]?id+'-'+visible[active].id:undefined" @focus="open" @click="!opened&&open()" @input="input" @keydown.down.prevent="move(1)" @keydown.up.prevent="move(-1)" @keydown.enter.prevent="opened&&choose(visible[active])" @keydown.esc.prevent="opened=false"><button v-if="modelValue" type="button" :aria-label="'Очистить: '+label" @click="emit('update:modelValue','');query=''">×</button></div>
    <div v-if="opened" class="search-results"><div class="search-count">Найдено: {{matches.length}}<template v-if="matches.length>60"> · показаны первые 60, уточните поиск</template></div><ul :id="id+'-list'" role="listbox" :aria-label="label"><li v-for="(option,i) in visible" :id="id+'-'+option.id" :key="option.id" role="option" :aria-selected="option.id===modelValue" :class="{highlighted:i===active}" @mousedown.prevent="choose(option)" @mouseover="active=i"><strong>{{option.name}}</strong><small v-if="option.department">{{option.department}}</small></li><li v-if="!visible.length" class="no-results">Ничего не найдено</li></ul></div>
  </div>
</template>
<style scoped>
.search-select{position:relative;margin:17px 0;min-width:0}.search-select>label{display:block;font-size:12px;font-weight:700;margin-bottom:7px}.search-control{position:relative}.search-control input{width:100%;padding-right:32px;font-size:12px}.search-control button{position:absolute;right:3px;top:3px;padding:7px;color:#708778}.search-results{position:absolute;top:100%;left:0;right:0;z-index:20;background:white;box-shadow:0 10px 25px #203f3325;border:1px solid #dce6df;border-radius:8px;margin-top:4px;overflow:hidden}.search-count{padding:10px;font-size:10px;color:#708778;border-bottom:1px solid #e5ebe6}.search-results ul{margin:0;padding:4px;list-style:none;max-height:280px;overflow:auto}.search-results li{padding:10px 8px;border-radius:5px;cursor:pointer;font-size:12px;overflow-wrap:anywhere}.search-results strong{font-weight:500}.search-results small{display:block;margin-top:4px}.highlighted{background:#edf5ee}.no-results{color:#8c968f}
</style>
