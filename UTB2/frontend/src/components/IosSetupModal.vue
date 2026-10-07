<template>
  <Teleport to="body">
    <div v-if="isOpen" class="modal-overlay" @click.self="close">
      <div class="modal-content">
        <div class="modal-header">
          <h2>📱 Расписание на экране блокировки iOS</h2>
          <button class="close-btn" @click="close">✕</button>
        </div>

        <div class="modal-body">
          <div class="step-card">
            <div class="step-num">1</div>
            <div class="step-info">
              <h3>Скачайте Быструю команду</h3>
              <p>Установите команду <strong>UTB</strong> в приложение «Команды».</p>
              <a
                :href="icloudShortcutUrl"
                target="_blank"
                class="btn-primary"
              >
                📥 Скачать UTB
              </a>
            </div>
          </div>

          <div class="step-card">
            <div class="step-num">2</div>
            <div class="step-info">
              <h3>Привяжите группу</h3>


              <a
                :href="runShortcutUrl"
                :class="['btn-secondary', { disabled: !groupId }]"
              >
                🔗 Привязать к iPhone
              </a>
            </div>
          </div>

          <div class="step-card">
            <div class="step-num">3</div>
            <div class="step-info">
              <h3>Настройте автосмену в 19:00</h3>
              <ol class="steps-list">
                <li>Откройте «Команды» ➔ вкладка <strong>«Автоматизация»</strong>.</li>
                <li>Нажмите <strong>«+»</strong> ➔ <strong>«Время суток»</strong> (19:00, Ежедневно).</li>
                <li>Выберите <strong>«Запускать немедленно»</strong>.</li>
                <li>Укажите команду <strong>UTB</strong>.</li>
              </ol>
            </div>
          </div>

          <div class="step-card">
                <div class="step-num">?</div>
                <div class="step-info">
                    <h3>Нужна помощь?</h3>
                    <p>Возникли проблемы с настройкой?</p>
                    <a
                    href="https://t.me/abramForexx"
                    target="_blank"
                    class="btn-primary"
                    >
                    💬 Написать в Telegram
                    </a>
                </div>
            </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  isOpen: Boolean
})

const emit = defineEmits(['close'])

const icloudShortcutUrl = 'https://www.icloud.com/shortcuts/fa3e2591f96d4e68a0bc75b437a28a65'

const groupId = ref('')

// Подтягиваем ID группы из localStorage при открытии окна
watch(() => props.isOpen, (newVal) => {
  if (newVal) {
    const saved = localStorage.getItem('user_group_id')
    groupId.value = ''
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        groupId.value = parsed.id || parsed
      } catch {
        groupId.value = saved
      }
    }
  }
})

const runShortcutUrl = computed(() => {
  if (!groupId.value) return '#'
  return `shortcuts://run-shortcut?name=UTB&input=${encodeURIComponent(groupId.value)}`
})

const close = () => {
  emit('close')
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
  padding: 16px;
}

.modal-content {
  background: #1c1c1e;
  border: 1px solid #2c2c2e;
  border-radius: 20px;
  width: 100%;
  max-width: 440px;
  max-height: 85vh;
  overflow-y: auto;
  padding: 20px;
  color: #fff;
  box-shadow: 0 10px 30px rgba(0,0,0,0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.modal-header h2 {
  font-size: 1.2rem;
  font-weight: 700;
}

.close-btn {
  background: #2c2c2e;
  border: none;
  color: #8e8e93;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  cursor: pointer;
  font-size: 0.9rem;
}

.modal-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.step-card {
  display: flex;
  gap: 12px;
  background: #2c2c2e/50;
  background-color: rgba(44, 44, 46, 0.4);
  border: 1px solid #3a3a3c;
  border-radius: 14px;
  padding: 14px;
}

.step-num {
  background: #0a84ff;
  color: #fff;
  font-weight: 700;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.85rem;
  flex-shrink: 0;
}

.step-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 0.85rem;
}

.step-info h3 {
  font-size: 0.95rem;
  font-weight: 600;
}

.step-info p {
  color: #aeaeb2;
}

.highlight {
  color: #30d158;
}

.warning {
  color: #ff9f0a;
}

.btn-primary, .btn-secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 14px;
  border-radius: 8px;
  text-decoration: none;
  font-weight: 600;
  font-size: 0.85rem;
  margin-top: 4px;
}

.btn-primary {
  background: #0a84ff;
  color: #fff;
}

.btn-secondary {
  background: #30d158;
  color: #fff;
}

.btn-secondary.disabled {
  background: #3a3a3c;
  color: #8e8e93;
  pointer-events: none;
}

.steps-list {
  padding-left: 16px;
  color: #aeaeb2;
  line-height: 1.5;
}
</style>
