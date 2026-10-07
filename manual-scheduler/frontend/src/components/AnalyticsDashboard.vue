<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
const emit = defineEmits(['unauthorized'])
const days = ref(30), report = ref(null), loading = ref(false), error = ref('')
let controller, timer, sequence = 0
const number = value => new Intl.NumberFormat('ru-RU').format(value ?? 0)
const date = value => new Date(value.length === 10 ? `${value}T12:00:00+05:00` : value).toLocaleDateString('ru-RU', {timeZone:'Asia/Almaty', day:'numeric',month:'short'})
const cards = computed(() => [
  ['Посетители сайта', report.value?.totals.visitors, 'Уникальные браузеры за выбранный период'],
  ['Визиты', report.value?.totals.visits, 'Новый визит после 30 минут бездействия'],
  ['Просмотры расписаний', report.value?.totals.schedule_views, 'Выбор группы, преподавателя или дня'],
  ['Активны за 5 минут', report.value?.totals.active, 'Посетители, недавно совершившие действие'],
  ['Повторные посетители', report.value?.totals.returning, 'Больше одного визита за выбранный период'],
  ['Ошибки загрузки', report.value?.totals.errors, 'Неудачные загрузки на студенческом сайте'],
])
const peak = computed(() => Math.max(1, ...(report.value?.daily || []).map(row => row.visitors)))
const labels = {phone:'Телефон',tablet:'Планшет',desktop:'Компьютер',unknown:'Неизвестно',student:'Студенты',teacher:'Преподаватели',Other:'Другой'}
const rankings = computed(() => [
  {title:'Популярные группы',unit:'Просмотры',rows:report.value?.groups || []},
  {title:'Популярные преподаватели',unit:'Просмотры',rows:report.value?.teachers || []},
  {title:'Устройства',unit:'Визиты',rows:report.value?.devices || []},
  {title:'Браузеры',unit:'Визиты',rows:report.value?.browsers || []},
])
async function refresh(){
  const ticket = ++sequence
  controller?.abort(); controller = new AbortController()
  loading.value = true; error.value = ''
  try {
    const response = await fetch(`/api/analytics?days=${days.value}`,{cache:'no-store',signal:controller.signal})
    if(response.status === 401){emit('unauthorized');return}
    const data = await response.json()
    if(!response.ok)throw new Error(typeof data.detail === 'string' ? data.detail : 'Не удалось загрузить статистику')
    if(ticket === sequence)report.value = data
  } catch(e){if(ticket === sequence && e.name !== 'AbortError')error.value = e.message || 'Не удалось подключиться к серверу'}
  finally{if(ticket === sequence)loading.value = false}
}
watch(days,()=>{report.value=null;refresh()})
function visible(){if(!document.hidden && !loading.value)refresh()}
onMounted(()=>{refresh();timer=setInterval(visible,60000);document.addEventListener('visibilitychange',visible)})
onUnmounted(()=>{sequence++;controller?.abort();clearInterval(timer);document.removeEventListener('visibilitychange',visible)})
</script>

<template>
  <section class="analytics" aria-labelledby="analytics-title" :aria-busy="loading">
    <div class="analytics-heading">
      <div><h1 id="analytics-title">Посещения okak.asia</h1><p class="muted">Как пользуются просмотром расписания</p></div>
      <div class="analytics-controls"><label>Период<select v-model.number="days"><option :value="1">Сегодня</option><option :value="7">7 дней</option><option :value="30">30 дней</option><option :value="90">90 дней</option><option :value="180">180 дней</option></select></label><button class="outline" :disabled="loading" @click="refresh">{{loading?'Обновляем…':'Обновить'}}</button></div>
    </div>
    <p v-if="error" class="alert error" role="alert">{{error}}<span v-if="report"> Показаны последние загруженные данные.</span></p>
    <p v-if="loading && !report" role="status" class="analytics-empty">Загружаем статистику…</p>
    <template v-if="report">
      <div class="analytics-cards"><article v-for="[title,value,hint] in cards" :key="title" class="analytics-card"><p>{{title}}</p><strong>{{number(value)}}</strong><small>{{hint}}</small></article></div>
      <p v-if="!report.first_event_at" class="analytics-empty">Посещений пока нет. Данные появятся после открытия сайта okak.asia посетителями.</p>
      <p v-else-if="!report.totals.visitors" class="analytics-empty">За выбранный период посещений нет. Попробуйте выбрать больший период.</p>
      <section class="analytics-chart">
        <div class="analytics-chart-heading"><h2>Посетители по дням</h2><span class="muted">{{date(report.daily[0].day)}} — {{date(report.daily.at(-1).day)}}</span></div>
        <svg viewBox="0 0 900 190" role="img" aria-label="График уникальных посетителей по дням. Точные значения доступны в таблице ниже.">
          <line x1="0" y1="165" x2="900" y2="165" stroke="#dce3df" />
          <g v-for="(row,i) in report.daily" :key="row.day"><rect :x="i*900/report.daily.length + 1" :y="165-row.visitors/peak*150" :width="Math.max(1,900/report.daily.length-2)" :height="row.visitors/peak*150" rx="2" fill="#32765b"><title>{{date(row.day)}}: {{number(row.visitors)}} посетителей, {{number(row.visits)}} визитов</title></rect></g>
          <text x="0" y="185" fill="#62756a" font-size="12">{{date(report.daily[0].day)}}</text><text x="900" y="185" text-anchor="end" fill="#62756a" font-size="12">{{date(report.daily.at(-1).day)}}</text>
        </svg>
        <details><summary>Показать значения по дням</summary><div class="analytics-table"><table><thead><tr><th>Дата</th><th>Посетители</th><th>Визиты</th></tr></thead><tbody><tr v-for="row in report.daily" :key="row.day"><td>{{date(row.day)}}</td><td>{{number(row.visitors)}}</td><td>{{number(row.visits)}}</td></tr></tbody></table></div></details>
      </section>
      <div class="analytics-rankings"><section v-for="ranking in rankings" :key="ranking.title" class="analytics-chart"><h2>{{ranking.title}}</h2><table v-if="ranking.rows.length"><thead><tr><th>Название</th><th>{{ranking.unit}}</th></tr></thead><tbody><tr v-for="row in ranking.rows" :key="`${row.id || ''}:${row.name}`"><td>{{labels[row.name] || row.name}}</td><td>{{number(row.count)}}</td></tr></tbody></table><p v-else class="muted">Пока нет данных</p></section></div>
      <p class="analytics-note">Посетитель — уникальный браузер, а не установленная личность. Один человек с разных устройств может учитываться несколько раз. Сумма посетителей по дням может быть больше числа за период. Автообновление расписания не увеличивает просмотры.</p>
      <p class="analytics-note">Дни считаются по времени Алматы. Данные хранятся {{report.retention_days}} дней. Обновлено: {{new Date(report.generated_at).toLocaleString('ru-RU',{timeZone:'Asia/Almaty'})}}<template v-if="report.first_event_at"> · Первые сохранённые данные: {{date(report.first_event_at)}}</template>. Страница обновляется каждую минуту.</p>
    </template>
  </section>
</template>

<style scoped>
.analytics{max-width:1400px;margin:0 auto}.analytics-heading,.analytics-controls,.analytics-chart-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}.analytics-heading{margin:8px 0 24px}.analytics-heading h1{font-size:26px;margin:0 0 8px}.analytics-controls label{display:flex;align-items:center;gap:10px;font-size:12px}.analytics-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:22px}.analytics-card,.analytics-chart{background:white;border:1px solid #dce3df;border-radius:14px;padding:22px}.analytics-card p{margin:0 0 8px;font-size:13px}.analytics-card strong{display:block;font-size:36px;color:#265c49;font-variant-numeric:tabular-nums;margin-bottom:8px}.analytics-card small{display:block;line-height:1.5}.analytics-chart h2{margin:0 0 12px}.analytics-chart svg{display:block;width:100%;height:auto;max-height:250px;margin:14px 0}.analytics-chart summary{cursor:pointer;font-size:12px;padding:10px 0}.analytics-table{max-height:320px;overflow:auto}.analytics table{width:100%;border-collapse:collapse;font-size:13px}.analytics th,.analytics td{text-align:left;padding:10px 0;border-bottom:1px solid #edf1ed;overflow-wrap:anywhere}.analytics th:last-child,.analytics td:last-child{text-align:right;padding-left:15px;font-variant-numeric:tabular-nums}.analytics-rankings{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0}.analytics-note{font-size:12px;color:#65776d;line-height:1.7}.analytics-empty{padding:22px;border:1px dashed #b8cdbf;border-radius:12px;color:#52745e}@media(max-width:750px){.analytics-heading{align-items:start;flex-direction:column}.analytics-cards{grid-template-columns:repeat(2,minmax(0,1fr))}.analytics-rankings{grid-template-columns:1fr}.analytics-card,.analytics-chart{padding:16px}.analytics-controls{flex-wrap:wrap}.analytics-heading h1{font-size:23px}.analytics-chart-heading{align-items:start;flex-direction:column}}@media(max-width:420px){.analytics-cards{grid-template-columns:1fr}}
</style>
