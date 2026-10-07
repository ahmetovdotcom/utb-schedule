<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  kind: { type: String, default: "student" },
  groups: {
    type: Array,
    required: true
  },
  selectedGroup: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['select-group'])

const searchQuery = ref('')
const isOpen = ref(false)

watch(
  () => props.selectedGroup,
  (newVal) => {
    if (newVal) {
      isOpen.value = false
    }
  },
  { immediate: true }
)

const filteredGroups = computed(() => {
  if (!searchQuery.value) return props.groups
  return props.groups.filter(g =>
    g.title.toLowerCase().includes(searchQuery.value.toLowerCase())
  )
})

const handleSelect = (group) => {
  emit('select-group', group)
  isOpen.value = false
  searchQuery.value = ''
}
</script>

<template>
  <div class="group-selector-wrapper">
    <!-- Компактная кнопка выбора группы в шапке -->
    <button
      v-if="selectedGroup && !isOpen"
      class="active-group-btn"
      @click="isOpen = true"
      :title="kind === 'teacher' ? 'Сменить преподавателя' : 'Сменить группу'"
    >
      <span class="icon">👥</span>
      <span class="group-name">{{ selectedGroup.title }}</span>
    </button>

    <!-- Кнопка, если группа ещё не выбрана -->
    <button
      v-else-if="!isOpen"
      class="active-group-btn highlight"
      @click="isOpen = true"
    >
      <span class="icon">👥</span>
      <span class="group-name">Выбрать</span>
    </button>

    <!-- Модальный экран выбора -->
    <div v-if="isOpen" class="modal-overlay" @click.self="isOpen = false">
      <div class="modal-content">
        <h2>{{ kind === 'teacher' ? 'Выберите преподавателя' : 'Выберите группу' }}</h2>

        <input
          v-model="searchQuery"
          type="text"
          :placeholder="kind === 'teacher' ? 'Поиск по имени...' : 'Поиск группы...'"
          class="search-input"
        />

        <div class="groups-list">
          <button
            v-for="group in filteredGroups"
            :key="group.id"
            class="group-item"
            :class="{ selected: selectedGroup?.id === group.id }"
            @click="handleSelect(group)"
          >
            {{ group.title }}
          </button>

          <div v-if="filteredGroups.length === 0" class="empty-search">
            Ничего не найдено
          </div>
        </div>

        <button class="close-btn" @click="isOpen = false">
          Отмена
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.active-group-btn {
  background-color: #1c1c1e;
  border: 1px solid #2c2c2e;
  color: #ffffff;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  white-space: nowrap;
  max-width: 130px; /* Чтобы длинное название группы не ломало верстку */
}

.active-group-btn.highlight {
  border-color: #0a84ff;
  color: #0a84ff;
}

.icon {
  font-size: 0.9rem;
  flex-shrink: 0;
}

.group-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 20px;
}

.modal-content {
  background-color: #1c1c1e;
  border: 1px solid #2c2c2e;
  border-radius: 24px;
  width: 100%;
  max-width: 400px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: 80vh;
}

.modal-content h2 {
  color: #fff;
  margin: 0;
  font-size: 1.3rem;
}

.search-input {
  background-color: #2c2c2e;
  border: none;
  color: #fff;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 1rem;
  outline: none;
}

.groups-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  max-height: 300px;
}

.group-item {
  background-color: transparent;
  border: none;
  color: #ffffff;
  padding: 14px 16px;
  border-radius: 12px;
  text-align: left;
  font-size: 1rem;
  cursor: pointer;
  transition: background-color 0.2s;
}

.group-item:hover, .group-item.selected {
  background-color: #2c2c2e;
  color: #0a84ff;
}

.close-btn {
  background: transparent;
  border: none;
  color: #8e8e93;
  padding: 10px;
  font-size: 0.95rem;
  cursor: pointer;
}

.empty-search {
  text-align: center;
  color: #8e8e93;
  padding: 20px 0;
}
</style>
