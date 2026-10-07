<script setup>
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import GroupSelector from './components/GroupSelector.vue'
import DayTabs from './components/DayTabs.vue'
import LessonCard from './components/LessonCard.vue'
import { scheduleApi } from './services/api'
import { track } from './services/analytics'

const groups = ref([])
const teachers = ref([])
const mode = ref(localStorage.getItem('schedule_mode') === 'teacher' ? 'teacher' : 'student')
const choices = computed(() => mode.value === 'teacher' ? teachers.value : groups.value)
const storageKey = () => mode.value === 'teacher' ? 'user_teacher_id' : 'user_group_id'
function restoreSelection() {
  const saved = localStorage.getItem(storageKey())
  selectedGroup.value = choices.value.find(item => String(item.id) === String(saved)) || null
  if (saved && !selectedGroup.value) {
    localStorage.removeItem(storageKey())
    notice.value = 'Выбранная запись больше недоступна. Выберите из обновлённого списка.'
  }
}
const selectedGroup = ref(null)
const currentDay = ref(new Date().getDay() || 7)
const lessons = ref([])
const isLoading = ref(false)
const publication = ref(null)
const error = ref('')
const notice = ref('')
let requestNumber = 0
let lastTrackedSchedule = null
let refreshing = false
let timer

async function fetchSchedule() {
  const ticket = ++requestNumber
  lessons.value = []
  if (!selectedGroup.value) { isLoading.value = false; lastTrackedSchedule = null; return }
  const selection = `${mode.value}:${selectedGroup.value.id}:${currentDay.value}`
  isLoading.value = true
  error.value = ''
  try {
    const data = await (mode.value === 'teacher' ? scheduleApi.getTeacherSchedule : scheduleApi.getSchedule)(selectedGroup.value.id, currentDay.value)
    if (ticket === requestNumber) {
      lessons.value = data
      if (selection !== lastTrackedSchedule) {
        track('schedule', mode.value, selectedGroup.value.id)
        lastTrackedSchedule = selection
      }
    }
  } catch (e) {
    if (ticket !== requestNumber) return
    track('error', mode.value, null, e.status ? 'http' : 'network')
    if (e.status === 404) {
      localStorage.removeItem(storageKey())
      selectedGroup.value = null
      notice.value = 'Запись больше недоступна. Выберите из обновлённого списка.'
      try { await refreshAll() }
      catch { error.value = 'Не удалось обновить список групп. Повторите подключение.' }
    } else {
      error.value = 'Не удалось обновить расписание. Проверьте соединение и повторите.'
    }
  } finally {
    if (ticket === requestNumber) isLoading.value = false
  }
}

async function refreshAll() {
  if (refreshing) return
  refreshing = true
  try {
    const [nextPublication, nextGroups, nextTeachers] = await Promise.all([
      scheduleApi.getPublication(), scheduleApi.getGroups(), scheduleApi.getTeachers(),
    ])
    publication.value = nextPublication
    groups.value = nextGroups
    error.value = ''
    teachers.value = nextTeachers
    restoreSelection()
  } catch {
    track('error', mode.value, null, 'load')
    ++requestNumber
    lessons.value = []
    isLoading.value = false
    error.value = 'Не удалось загрузить актуальное расписание. Проверьте соединение и повторите.'
  } finally { refreshing = false }
}

function handleGroupSelect(group) {
  notice.value = ''
  selectedGroup.value = group
  localStorage.setItem(storageKey(), group.id)
}
function onVisible() {
  if (document.visibilityState === 'visible') refreshAll()
}
onMounted(() => {
  track('open', mode.value)
  refreshAll()
  timer = setInterval(onVisible, 60000)
  document.addEventListener('visibilitychange', onVisible)
  window.addEventListener('online', refreshAll)
})
onUnmounted(() => {
  clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisible)
  window.removeEventListener('online', refreshAll)
})
watch(mode, () => {
  localStorage.setItem('schedule_mode', mode.value)
  track('mode', mode.value)
  ++requestNumber
  lessons.value = []
  notice.value = ''
  restoreSelection()
})
watch([selectedGroup, currentDay, mode], fetchSchedule)
// Successful selection changes are tracked in fetchSchedule; refreshes are not views.
</script>

<template>
  <div class="app-container">
    <header class="header">
      <h1 class="logo">Расписание</h1>

      <div class="header-actions">
        <button
          type="button"
          class="audience-switch"
          :aria-pressed="mode === 'teacher'"
          :aria-label="mode === 'student' ? 'Студент. Переключить на преподавателя' : 'Преподаватель. Переключить на студента'"
          :title="mode === 'student' ? 'Студент → Преподаватель' : 'Преподаватель → Студент'"
          @click="mode = mode === 'student' ? 'teacher' : 'student'"
        >
          <span aria-hidden="true">{{ mode === 'student' ? '🎓' : '👨‍🏫' }}</span>
        </button>

        <GroupSelector
          v-if="choices.length"
          :key="mode"
          :kind="mode"
          :groups="choices"
          :selected-group="selectedGroup"
          @select-group="handleGroupSelect"
        />
      </div>
    </header>

    <p v-if="publication?.published" class="publication-meta">
      Официальное расписание · Обновлено {{ new Date(publication.published_at).toLocaleString('ru-RU') }}
    </p>
    <p v-if="notice" role="status" class="state-msg">{{ notice }}</p>
    <div v-if="error" role="alert" class="state-msg">
      {{ error }} <button @click="refreshAll" type="button">Повторить</button>
    </div>
    <main v-else-if="selectedGroup" class="main-content">
      <DayTabs v-model="currentDay" />

      <div class="schedule-section">
        <div v-if="isLoading" class="state-msg">Загрузка...</div>

        <div v-else-if="lessons.length === 0" class="state-msg empty">
          🎉 Занятий нет, можно отдыхать!
        </div>

        <div v-else class="lessons-list">
          <LessonCard
            v-for="lesson in lessons"
            :key="lesson.id"
            :time="lesson.time"
            :subject="lesson.subject"
            :room="lesson.room" :delivery="lesson.delivery" :online_url="lesson.online_url" :meeting_id="lesson.meeting_id" :passcode="lesson.passcode"
            :groups="lesson.groups"
          />
        </div>
      </div>
    </main>

    <div v-else class="welcome-screen">
      <p v-if="publication?.published === false">Расписание ещё не опубликовано.</p>
      <p v-else-if="publication?.published && !choices.length">{{ mode === 'teacher' ? 'Преподаватели пока не опубликованы. Сотруднику нужно повторно опубликовать расписание.' : 'В опубликованном расписании пока нет групп.' }}</p>
      <p v-else-if="!publication">Загрузка расписания…</p>
      <p v-else>{{ mode === 'teacher' ? 'Выберите преподавателя вверху, чтобы посмотреть расписание' : 'Выберите вашу группу вверху, чтобы посмотреть расписание' }}</p>
    </div>

    <details class="usage-notice">
      <summary>О статистике посещений</summary>
      <p>Мы учитываем открытия приложения и просмотры расписания, тип устройства и браузера.
        Для подсчёта повторных посещений в браузере хранится случайный идентификатор.
        Имена посетителей и IP-адреса в статистику не записываются. Срок хранения событий — 180 дней.
        Сигналы браузера Do Not Track и Global Privacy Control отключают сбор.</p>
    </details>
  </div>
</template>

<style>
.usage-notice { margin-top: 24px; color: #8e8e93; font-size: 0.75rem; line-height: 1.6; }
.usage-notice summary { cursor: pointer; }
.usage-notice p { margin-top: 8px; }
.audience-switch {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 28px;
  padding: 0;
  flex-shrink: 0;
  font-size: 1.3rem;
  line-height: 1;
  color: #fff;
  background: #1c1c1e;
  border: 1px solid #2c2c2e;
  border-radius: 8px;
  cursor: pointer;
}
.audience-switch[aria-pressed="true"] { border-color: #399bff; background: #12304e; }
.audience-switch:focus-visible { outline: 2px solid #399bff; outline-offset: 2px; }

.publication-meta { font-size: 0.8rem; color: #8e8e93; line-height: 1.5; margin: 0; }

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, sans-serif;
}

body {
  background-color: #000000;
  color: #ffffff;
  display: flex;
  justify-content: center;
  min-height: 100vh;
}

#app {
  width: 100%;
  max-width: 480px;
}

.app-container {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 10px;
}

.logo {
  font-size: 1.25rem;
  font-weight: 700;
  color: #ffffff;
  white-space: nowrap;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

@media (max-width: 380px) {
  .logo { font-size: 1rem; }
  .header-actions { flex: 1; min-width: 0; justify-content: flex-end; }
  .header-actions .active-group-btn { max-width: 85px; font-size: 0.75rem; }
}

.main-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.lessons-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.state-msg {
  text-align: center;
  color: #8e8e93;
  padding: 40px 0;
  font-size: 1.05rem;
}

.welcome-screen {
  text-align: center;
  color: #8e8e93;
  margin-top: 60px;
}
</style>