<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import SearchSelect from './components/SearchSelect.vue'
import AnalyticsDashboard from './components/AnalyticsDashboard.vue'
const authenticated = ref(false), authLoading = ref(true), loginBusy = ref(false), connection = ref('Подключение…')
const loginForm = reactive({login:'admin',password:''})
let events = null
const publishing = ref(false)
const state = reactive({ references: [], lessons: [], days: ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота'], room_types: {} })
const page = ref('schedule'), view = ref('rooms'), day = ref(1), selected = ref(''), building = ref(''), search = ref('')
const error = ref(''), notice = ref(''), busy = ref(false), loading = ref(true), checks = ref([]), checking = ref(false), selectedCell = ref(null)
const referenceEditId = ref(null)
const lessonDialog = ref(null), contextMenu = ref(null)
const editVersion = ref(null)
const editId = ref(null), refKind = ref('groups'), referenceSearch = ref(''), groupSearch = ref('')
const form = reactive({ teacher_id: '', subject_id: '', group_ids: [], lesson_type: 'practice' })
const newRef = reactive({ name: '', department: '', capacity: 30, students: 20, course: 1, building: 'Главный корпус', room_type: 'classroom' })
const hours = Array.from({length:13},(_,i)=>i+8)
const kinds = { groups: 'Группы', teachers: 'Преподаватели', subjects: 'Предметы', rooms: 'Кабинеты', buildings: 'Корпуса', departments: 'Кафедры' }
const typeLabels = { lecture: 'Лекция', practice: 'Практика', lab: 'Лабораторная' }
const byKind = kind => state.references.filter(r=>r.kind===kind)
const lookup = id => state.references.find(r=>r.id===Number(id)) || {name:'—'}
const rooms = computed(()=>byKind('rooms').filter(r=>(!building.value || r.building===building.value) && `${r.name} ${r.department}`.toLowerCase().includes(search.value.toLowerCase())))
const buildings = computed(()=>[...new Set([...byKind('buildings').map(r=>r.name), ...byKind('rooms').map(r=>r.building)])])
const groups = computed(()=>byKind('groups').filter(g=>g.name.toLowerCase().includes(groupSearch.value.toLowerCase())))
const ready = computed(()=>!!form.teacher_id && !!form.subject_id && form.group_ids.length>0)
const selectedGroups = computed(()=>form.group_ids.map(lookup))
const studentCount = computed(()=>selectedGroups.value.reduce((n,g)=>n+g.students,0))
const displayedRefs = computed(()=>byKind(refKind.value).filter(r=>r.name.toLowerCase().includes(referenceSearch.value.toLowerCase())))
const weekLessons = computed(()=>state.lessons.filter(l=>view.value==='groups' ? l.group_ids.includes(Number(selected.value)) : l.teacher_id===Number(selected.value)))
const cellLesson = (room, hour) => state.lessons.find(l=>l.day===day.value&&l.room_id===room&&l.slot===hour)
const cellCheck = (room, hour) => checks.value.find(c=>c.room_id===room&&c.slot===hour)
function cellClass(room,hour){const c=cellCheck(room,hour);return selectedCell.value?.room_id===room&&selectedCell.value?.slot===hour?'chosen':c?.conflicts.length?'blocked':c?.warnings.length?'caution':c?'available':''}
async function api(path, method='GET', data){
  const response=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json'},...(data?{body:JSON.stringify(data)}:{})})
  const body=await response.json()
  if(response.status===401){expireSession()}
  if(!response.ok) throw body.detail || 'Ошибка запроса'
  return body
}
function message(e){return typeof e==='string'?e:Array.isArray(e)?e.map(x=>x.msg).join('; '):[...(e.conflicts||[]).map(c=>`${c.message}: ауд. ${c.room}, ${c.groups.join(', ')}`),...(e.warnings||[])].join('\n')||'Не удалось выполнить действие'}
async function load(){
  try{
    const data=await api('/state')
    if(authenticated.value && (state.revision===undefined || data.revision>=state.revision))Object.assign(state,data)
  }catch(e){error.value=message(e)}finally{loading.value=false}
}
function expireSession(){authenticated.value=false;events?.close();events=null;lessonDialog.value?.close();contextMenu.value=null;connection.value='Вход не выполнен'}
function connectEvents(){
  events?.close()
  const source=new EventSource('/api/events');events=source
  source.onopen=()=>{connection.value='Онлайн · изменения синхронизируются'}
  source.addEventListener('changed',()=>load())
  source.addEventListener('expired',()=>{expireSession();error.value='Сеанс завершён. Войдите снова.'})
  source.onerror=()=>{connection.value='Связь потеряна · переподключение…';fetch('/api/auth/me').then(r=>{if(r.status===401)expireSession()}).catch(()=>{})}
}
async function checkAuth(){
  try{const response=await fetch('/api/auth/me');if(response.ok){authenticated.value=true;await load();connectEvents()}}
  catch{error.value='Сервер недоступен. Попробуйте войти позже.'}
  finally{authLoading.value=false}
}
async function login(){
  loginBusy.value=true;error.value=''
  try{await api('/auth/login','POST',loginForm);loginForm.password='';authenticated.value=true;state.revision=undefined;await load();connectEvents()}
  catch(e){error.value=message(e)}finally{loginBusy.value=false}
}
async function publishSchedule(){
  if(publishing.value)return
  if(!window.confirm(`Опубликовать всё расписание в UTB2? Текущая опубликованная версия будет заменена. Занятий в редакторе: ${state.lessons.length}.`))return
  publishing.value=true;error.value='';notice.value=''
  try{const result=await api('/publication','POST');notice.value=`Расписание опубликовано в UTB2. Групп: ${result.groups_count}.`;await load()}
  catch(e){error.value=message(e);await load()}finally{publishing.value=false}
}
async function logout(){
  try{await api('/auth/logout','POST');expireSession();state.references=[];state.lessons=[];state.revision=undefined;reset();notice.value=''}catch(e){error.value=message(e)}
}
const staleEdit = computed(()=>editId.value && state.lessons.find(l=>l.id===editId.value)?.version!==editVersion.value)
function reloadEdited(){const row=state.lessons.find(l=>l.id===editId.value);if(row&&window.confirm('Загрузить актуальную пару? Введённые в окне изменения будут сброшены.'))edit(row,false)}
let sequence=0
async function refreshChecks(){
  const seq=++sequence; checks.value=[]
  if(!ready.value||!byKind('rooms').length){checking.value=false;return}
  checking.value=true
  try{const data=await api('/options'+(editId.value?`?exclude=${editId.value}`:''),'POST',{...form,day:day.value,slot:8,room_id:byKind('rooms')[0].id});if(seq===sequence)checks.value=data}
  catch(e){if(seq===sequence)error.value=message(e)}finally{if(seq===sequence)checking.value=false}
}
watch(()=>[form.teacher_id,form.subject_id,[...form.group_ids].join(','),form.lesson_type,day.value,editId.value,state.lessons,state.references],refreshChecks)
function chooseDay(value){day.value=value;selectedCell.value=null}
watch(view,()=>selected.value='')
watch(refKind,()=>{referenceEditId.value=null;newRef.name=''})
function reset(){editId.value=null;editVersion.value=null;selectedCell.value=null;form.teacher_id='';form.subject_id='';form.group_ids=[];error.value=''}
function edit(lesson,show=true){Object.assign(form,{teacher_id:lesson.teacher_id,subject_id:lesson.subject_id,group_ids:[...lesson.group_ids],lesson_type:lesson.lesson_type});editId.value=lesson.id;editVersion.value=lesson.version;day.value=lesson.day;selectedCell.value={room_id:lesson.room_id,slot:lesson.slot};error.value='';notice.value='';contextMenu.value=null;if(show)lessonDialog.value.showModal()}
async function saveAt(room_id,slot){
  if(busy.value)return
  selectedCell.value={room_id,slot}
  if(!ready.value){error.value='Выберите преподавателя, предмет и группы';return}
  error.value='';notice.value='';busy.value=true
  const data={...form,room_id,slot,day:day.value,accept_warnings:false,expected_version:editId.value?editVersion.value:null}
  const path='/lessons'+(editId.value?`/${editId.value}`:'');const method=editId.value?'PUT':'POST'
  try{
    try{await api(path,method,data)}catch(e){
      if(e.warnings?.length&&!e.conflicts?.length&&window.confirm(message(e)+'\n\nВсё равно сохранить?'))await api(path,method,{...data,accept_warnings:true})
      else throw e
    }
    notice.value=editId.value?'Занятие изменено':'Занятие добавлено. Можно поставить следующее';lessonDialog.value.close();reset();await load()
  }catch(e){error.value=message(e);await load()}finally{busy.value=false}
}
function clickCell(room,hour){
  if(busy.value)return
  reset();groupSearch.value='';contextMenu.value=null
  selectedCell.value={room_id:room,slot:hour}
  lessonDialog.value.showModal()
}
function closeDialog(){if(busy.value)return;lessonDialog.value.close();reset()}
async function remove(lesson){
  contextMenu.value=null
  if(busy.value||!window.confirm('Удалить это занятие для всех его групп?'))return
  busy.value=true
  try{await api('/lessons/'+lesson.id+'?expected_version='+encodeURIComponent(lesson.version),'DELETE');await load();notice.value='Занятие удалено'}catch(e){error.value=message(e)}finally{busy.value=false}
}
function copy(lesson){edit(lesson);editId.value=null;notice.value='Выберите другое время или кабинет для копии'}
function openContext(event,lesson){
  if(busy.value)return
  const rect=event.currentTarget.getBoundingClientRect()
  contextMenu.value={lesson,x:Math.max(8,Math.min(event.clientX||rect.left,window.innerWidth-200)),y:Math.max(8,Math.min(event.clientY||rect.bottom,window.innerHeight-155))}
  nextTick(()=>document.querySelector('.context-menu button')?.focus())
}
function dismissContext(){contextMenu.value=null}
function contextKeys(event){if(event.key==='Escape')dismissContext()}
function drag(event,l){event.dataTransfer.setData('text/plain',String(l.id));event.dataTransfer.effectAllowed='move'}
async function drop(event,room,hour){const lesson=state.lessons.find(l=>l.id===Number(event.dataTransfer.getData('text/plain')));if(!lesson)return;const targetDay=day.value;edit(lesson,false);day.value=targetDay;await saveAt(room,hour)}
async function addRef(){busy.value=true;error.value='';try{await api('/references/'+(referenceEditId.value||refKind.value),referenceEditId.value?'PUT':'POST',{...newRef,expected_version:referenceEditId.value?newRef.version:null});newRef.name='';notice.value=referenceEditId.value?'Запись изменена':'Запись добавлена';referenceEditId.value=null;await load()}catch(e){error.value=message(e)}finally{busy.value=false}}
function editRef(r){referenceEditId.value=r.id;Object.assign(newRef,r)}
async function deleteRef(r){if(!window.confirm(`Удалить «${r.name}»?`))return;try{await api('/references/'+r.id+'?expected_version='+encodeURIComponent(r.version),'DELETE');await load()}catch(e){error.value=message(e)}}
async function demo(){busy.value=true;try{await api('/demo','POST');await load();notice.value='Пример загружен'}catch(e){error.value=message(e)}finally{busy.value=false}}
onMounted(()=>{checkAuth();window.addEventListener('click',dismissContext);window.addEventListener('keydown',contextKeys);window.addEventListener('resize',dismissContext);window.addEventListener('scroll',dismissContext,true)})
onUnmounted(()=>{events?.close();window.removeEventListener('click',dismissContext);window.removeEventListener('keydown',contextKeys);window.removeEventListener('resize',dismissContext);window.removeEventListener('scroll',dismissContext,true)})
</script>

<template>
  <header class="header"><a class="brand" href="#" @click.prevent="page='schedule'"><span class="logo">▦</span><span>Расписание</span></a><nav v-if="authenticated"><button :class="{active:page==='schedule'}" @click="page='schedule'">Расписание</button><button :class="{active:page==='references'}" @click="page='references'">Справочники</button><button :class="{active:page==='analytics'}" @click="page='analytics'">Статистика</button></nav><span v-if="authenticated" class="local" role="status"><i :class="{offline:!connection.startsWith('Онлайн')}"></i>{{connection}}</span><button v-if="authenticated" class="primary" :disabled="publishing || busy || loading" @click="publishSchedule">{{publishing?'Публикуем…':'Опубликовать'}}</button><button v-if="authenticated" @click="logout">Выйти</button></header>
  <section v-if="authLoading" class="login-wrap">Проверяем вход…</section>
  <section v-else-if="!authenticated" class="login-wrap"><form class="panel login-panel" @submit.prevent="login"><h1>Вход в расписание</h1><p class="muted">Общий аккаунт сотрудников</p><p v-if="error" class="alert error" role="alert">{{error}}</p><label>Логин<input v-model="loginForm.login" autocomplete="username" required maxlength="120"></label><label>Пароль<input v-model="loginForm.password" type="password" autocomplete="current-password" required maxlength="256"></label><button class="primary wide" :disabled="loginBusy">{{loginBusy?'Входим…':'Войти'}}</button></form></section>
  <main v-if="authenticated">
    <div v-if="error" class="alert error" role="alert">{{error}}<button @click="error=''" aria-label="Закрыть ошибку">×</button></div><div v-if="notice" class="alert info" role="status">{{notice}}<button @click="notice=''" aria-label="Закрыть сообщение">×</button></div>
    <AnalyticsDashboard v-if="page==='analytics'" @unauthorized="expireSession" />
    <p v-if="page!=='analytics' && state.publication" class="muted publication-status" role="status"><template v-if="state.publication.published_at">Опубликовано: {{new Date(state.publication.published_at).toLocaleString('ru-RU')}} · {{state.publication.dirty?'Есть неопубликованные изменения':'Все изменения опубликованы'}}</template><template v-else>Расписание ещё не опубликовано в UTB2</template><span v-if="state.publication.last_status==='unconfirmed'"> · Последняя отправка не подтверждена — повторите публикацию</span><span v-else-if="state.publication.last_status==='pending'"> · Ожидаем подтверждения UTB2</span><span v-if="!state.publication.configured"> · Подключение к UTB2 не настроено</span></p>
    <p v-if="loading">Загружаем расписание…</p>
    <section v-else-if="page!=='analytics' && !state.references.length" class="empty"><span>▦</span><h2>Начните с чистого листа</h2><p>Добавьте справочники или попробуйте редактор на небольшом примере.</p><button class="primary" @click="page='references'">Заполнить справочники</button> <button class="outline" :disabled="busy" @click="demo">Загрузить пример</button></section>
    <template v-if="page==='schedule' && state.references.length">
      <div class="toolbar"><div class="segmented"><button v-for="(label,key) in {rooms:'По кабинетам',groups:'Неделя группы',teachers:'Неделя преподавателя'}" :class="{active:view===key}" @click="view=key">{{label}}</button></div><span class="muted">Занятий в расписании: {{state.lessons.length}}</span></div>
      <div v-if="view==='rooms'" class="workspace">
        <section class="board"><div class="board-head"><div class="days"><button v-for="(d,i) in state.days" :class="{active:day===i+1}" @click="chooseDay(i+1)">{{['Пн','Вт','Ср','Чт','Пт','Сб'][i]}}</button></div><select v-model="building" aria-label="Корпус"><option value="">Все корпуса</option><option v-for="b in buildings">{{b}}</option></select><input v-model="search" placeholder="Найти кабинет…" aria-label="Поиск кабинета"></div>
          <div class="table-scroll"><table class="grid"><thead><tr><th>Кабинет <small>{{state.days[day-1]}}</small></th><th v-for="h in hours">{{h}}:00<small>{{h}}:50</small></th></tr></thead><tbody><tr v-for="room in rooms"><th><strong>{{room.name}}</strong><span>{{room.capacity}} мест · {{state.room_types[room.room_type]}}</span><small>{{room.department || room.building}}</small></th><td v-for="h in hours" :class="cellClass(room.id,h)" @dragover.prevent @drop.prevent="drop($event,room.id,h)"><button v-if="cellLesson(room.id,h)" class="lesson" :title="cellLesson(room.id,h).warnings?.join('\n')" draggable="true" @dragstart="drag($event,cellLesson(room.id,h))" @contextmenu.prevent.stop="openContext($event,cellLesson(room.id,h))" @keydown.shift.f10.prevent="openContext($event,cellLesson(room.id,h))"><strong><span v-if="cellLesson(room.id,h).warnings?.length">⚠ </span>{{lookup(cellLesson(room.id,h).teacher_id).name}}</strong><span>{{lookup(cellLesson(room.id,h).subject_id).name}}</span><small>{{cellLesson(room.id,h).group_ids.map(g=>lookup(g).name).join(', ')}}</small></button><button v-else class="empty-cell" :disabled="busy" :aria-label="`${room.name}, ${h}:00 — поставить занятие`" :title="cellCheck(room.id,h)?.conflicts.map(c=>c.message).concat(cellCheck(room.id,h)?.warnings||[]).join('\n')" @click="clickCell(room.id,h)">+</button></td></tr></tbody></table></div><p v-if="!rooms.length" class="muted pad">Кабинетов пока нет или они не подходят под фильтр.</p><div class="board-foot">Добавить занятие: + · Изменить или удалить: правая кнопка мыши · Перенести: перетащите карточку</div>
        </section>

      </div>
      <section v-else class="board"><div class="board-head"><SearchSelect v-model="selected" :options="byKind(view)" :label="view==='groups'?'Группа':'Преподаватель'" placeholder="Начните вводить название…"/><span class="muted">{{weekLessons.length}} занятий за неделю</span></div><div v-if="selected" class="table-scroll"><table class="grid week"><thead><tr><th>Время</th><th v-for="d in state.days">{{d}}</th></tr></thead><tbody><tr v-for="h in hours"><th>{{h}}:00</th><td v-for="(d,i) in state.days"><button v-for="l in weekLessons.filter(l=>l.day===i+1&&l.slot===h)" class="lesson" @contextmenu.prevent.stop="openContext($event,l)" @keydown.shift.f10.prevent="openContext($event,l)"><strong>{{lookup(l.subject_id).name}}</strong><span>{{lookup(l.teacher_id).name}}</span><small>Ауд. {{lookup(l.room_id).name}} · {{l.group_ids.map(g=>lookup(g).name).join(', ')}}</small></button></td></tr></tbody></table></div><p v-else class="pad muted">Выберите {{view==='groups'?'группу':'преподавателя'}}, чтобы увидеть неделю.</p></section>
    </template>
    <section v-if="page==='references'" class="references"><div class="board"><div class="board-head segmented"><button v-for="(label,key) in kinds" :class="{active:refKind===key}" @click="refKind=key">{{label}}</button></div><div class="pad"><input v-model="referenceSearch" placeholder="Поиск…" aria-label="Поиск по справочнику"></div><div class="ref-row" v-for="r in displayedRefs"><div><strong>{{r.name}}</strong><small v-if="['rooms','teachers','groups'].includes(refKind)">{{r.department || 'Без кафедры'}}<template v-if="refKind==='groups'"> · {{r.course ? r.course + ' курс' : 'Курс не указан'}} · {{r.students}} студентов</template><template v-if="refKind==='rooms'"> · {{r.capacity}} мест · {{state.room_types[r.room_type]}}</template></small></div><div><button class="text" @click="editRef(r)">Изменить</button> · <button class="text danger" @click="deleteRef(r)">Удалить</button></div></div><p v-if="!displayedRefs.length" class="pad muted">Пока нет записей.</p></div><form class="panel" @submit.prevent="addRef"><div class="panel-title"><h2>{{referenceEditId?'Изменить запись':'Добавить запись'}}</h2><button v-if="referenceEditId" type="button" class="text" @click="referenceEditId=null;newRef.name=''">Отмена</button></div><label>{{refKind==='groups'?'Код группы':refKind==='teachers'?'ФИО преподавателя':refKind==='rooms'?'Номер кабинета':refKind==='buildings'?'Название корпуса':refKind==='departments'?'Название кафедры':'Название предмета'}}<input required maxlength="512" v-model="newRef.name"></label><label v-if="['rooms','teachers','groups'].includes(refKind)">Кафедра <small>необязательно</small><select v-model="newRef.department"><option value="">Без кафедры</option><option v-for="d in [...new Set([...byKind('departments').map(r=>r.name), ...state.references.map(r=>r.department).filter(Boolean)])]" :value="d">{{d}}</option></select></label><template v-if="refKind==='groups'"><label>Курс<select v-model.number="newRef.course"><option :value="0">Курс не указан</option><option v-for="n in 8" :value="n">{{n}} курс</option></select></label><label>Количество студентов<input type="number" min="1" max="5000" v-model.number="newRef.students" required></label></template><template v-if="refKind==='rooms'"><label>Вместимость<input type="number" min="1" max="5000" v-model.number="newRef.capacity" required></label><label>Корпус<select v-model="newRef.building" required><option value="" disabled>Выберите корпус</option><option v-for="b in buildings" :value="b">{{b}}</option></select></label><label>Тип кабинета<select v-model="newRef.room_type"><option v-for="(label,key) in state.room_types" :value="key">{{label}}</option></select></label></template><button class="primary wide" :disabled="busy">{{referenceEditId?'Сохранить':'Добавить'}}</button></form></section>
    <dialog ref="lessonDialog" class="lesson-dialog" aria-labelledby="lesson-title" @cancel.prevent="closeDialog" @click="($event.target===lessonDialog)&&closeDialog()">
        <div class="panel lesson-form"><div class="panel-title"><h2 id="lesson-title">{{editId?'Изменить занятие':'Добавить занятие'}}</h2><button class="text" :disabled="busy" @click="closeDialog" aria-label="Закрыть окно">✕</button></div>
          <div v-if="staleEdit" class="alert error" role="alert">Эта пара изменена или удалена другим сотрудником. Ваши поля сохранены в окне.<button type="button" class="text" @click="reloadEdited">Обновить</button></div><div v-if="error" class="alert error" role="alert">{{error}}</div>
          <div v-if="selectedCell" class="placement-fields"><label>День<select v-model.number="day"><option v-for="(d,i) in state.days" :value="i+1">{{d}}</option></select></label><label>Время<select v-model.number="selectedCell.slot"><option v-for="h in hours" :value="h">{{h}}:00</option></select></label></div>
          <SearchSelect v-if="selectedCell" v-model="selectedCell.room_id" :options="byKind('rooms')" label="Кабинет" placeholder="Найти кабинет…"/>
          <SearchSelect v-model="form.teacher_id" :options="byKind('teachers')" label="Преподаватель" placeholder="Поиск по ФИО или кафедре…"/><SearchSelect v-model="form.subject_id" :options="byKind('subjects')" label="Предмет" placeholder="Поиск по названию предмета…"/><label>Тип занятия<select v-model="form.lesson_type"><option v-for="(v,k) in typeLabels" :value="k">{{v}}</option></select></label>
          <label>Группы / поток<input v-model="groupSearch" placeholder="Найти группу…"></label><div class="group-list"><label v-for="g in groups" class="check"><input type="checkbox" :value="g.id" v-model="form.group_ids"><span>{{g.name}}<small>{{g.course ? g.course + ' курс' : 'Курс не указан'}} · {{g.students}} студентов</small></span></label><p v-if="!groups.length" class="muted">Группы не найдены</p></div><div class="count">Групп: {{form.group_ids.length}} · студентов: {{studentCount}}</div>
          <div v-if="selectedCell && ready" class="fit-preview"><p v-if="checking">Проверяем…</p><template v-else><p v-for="c in cellCheck(selectedCell.room_id,selectedCell.slot)?.conflicts" class="danger">{{c.message}} · ауд. {{c.room}} · {{c.groups.join(', ')}}</p><p v-for="warning in cellCheck(selectedCell.room_id,selectedCell.slot)?.warnings">⚠ {{warning}}</p></template></div><p v-if="selectedCell" class="destination">{{state.days[day-1]}}, {{selectedCell.slot}}:00 · ауд. {{lookup(selectedCell.room_id).name}}</p><button v-if="selectedCell" class="primary wide" :disabled="!ready||busy||!selectedCell.room_id" @click="saveAt(selectedCell.room_id,selectedCell.slot)">{{busy?'Сохраняем…':editId?'Сохранить изменения':'Поставить пару'}}</button>
        </div>
    </dialog>
    <div v-if="contextMenu" class="context-menu" role="menu" aria-label="Действия с занятием" :style="{left:contextMenu.x+'px',top:contextMenu.y+'px'}" @click.stop @contextmenu.prevent>
      <button role="menuitem" @click="edit(contextMenu.lesson)">Изменить</button>
      <button role="menuitem" @click="copy(contextMenu.lesson)">Копировать</button>
      <button role="menuitem" class="danger" @click="remove(contextMenu.lesson)">Удалить</button>
    </div>
  </main>
</template>
