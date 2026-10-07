<script setup>
const props = defineProps({
  modelValue: {
    type: Number,
    required: true
  },
  days: {
    type: Array,
    default: () => [
      { id: 1, short: 'Пн' },
      { id: 2, short: 'Вт' },
      { id: 3, short: 'Ср' },
      { id: 4, short: 'Чт' },
      { id: 5, short: 'Пт' },
      { id: 6, short: 'Сб' },
      { id: 7, short: 'Вс' }
    ]
  }
})

defineEmits(['update:modelValue'])
</script>

<template>
  <div class="tabs-container">
    <button
      v-for="day in days"
      :key="day.id"
      class="tab-btn"
      :class="{ active: modelValue === day.id }"
      @click="$emit('update:modelValue', day.id)"
    >
      {{ day.short }}
    </button>
  </div>
</template>

<style scoped>
.tabs-container {
  display: flex;
  background-color: #1c1c1e;
  padding: 4px;
  border-radius: 14px;
  gap: 2px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.tabs-container::-webkit-scrollbar {
  display: none;
}

.tab-btn {
  flex: 1;
  min-width: 42px;
  background: transparent;
  border: none;
  color: #8e8e93;
  padding: 10px 0;
  font-size: 0.9rem;
  font-weight: 600;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tab-btn.active {
  background-color: #0a84ff;
  color: #ffffff;
  box-shadow: 0 2px 8px rgba(10, 132, 255, 0.4);
}
</style>