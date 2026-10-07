<script setup>
defineProps({
  groups: { type: Array, default: () => [] },
  time: {
    type: String,
    required: true
  },
  subject: {
    type: String,
    required: true
  },
  room: {
    type: String,
    default: null
  }
})
</script>

<template>
  <div class="lesson-card">
    <div class="time-badge">{{ time }}</div>
    <div class="info">
      <h3 class="subject">{{ subject }}</h3>
      <span v-if="groups.length" class="room">Группы: {{ groups.join(', ') }}</span>
      <span v-if="room" class="room">Аудитория: {{ room }}</span>
    </div>
  </div>
</template>

<style scoped>
.lesson-card {
  background-color: #1c1c1e;
  border: 1px solid #2c2c2e;
  border-radius: 16px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: transform 0.2s ease, background-color 0.2s ease;
}

.lesson-card:active {
  transform: scale(0.98);
  background-color: #2c2c2e;
}

.time-badge {
  background-color: rgba(10, 132, 255, 0.15);
  color: #0a84ff;
  font-weight: 700;
  font-size: 0.95rem;
  padding: 10px 14px;
  border-radius: 12px;
  white-space: nowrap;
}

.info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.subject {
  color: #ffffff;
  font-size: 1.05rem;
  font-weight: 600;
  margin: 0;
  line-height: 1.3;
  word-break: break-word;
}

.room {
  color: #8e8e93;
  font-size: 0.85rem;
}
</style>