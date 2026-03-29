<template>
  <form class="render-form" @submit.prevent="handleSubmit">
    <div class="render-form__fields">
      <label class="render-form__label">
        Camera
        <select v-model="form.camera" class="render-form__input" required>
          <option value="" disabled>Select camera</option>
          <option v-for="cam in cameraNames" :key="cam" :value="cam">{{ cam }}</option>
        </select>
      </label>

      <label class="render-form__label">
        Date From
        <input type="date" v-model="form.date_from" class="render-form__input" required />
      </label>

      <label class="render-form__label">
        Date To
        <input type="date" v-model="form.date_to" class="render-form__input" required />
      </label>

      <label class="render-form__label">
        Time From
        <input type="time" v-model="form.time_from" class="render-form__input" />
      </label>

      <label class="render-form__label">
        Time To
        <input type="time" v-model="form.time_to" class="render-form__input" />
      </label>

      <label class="render-form__label">
        FPS
        <input type="number" v-model.number="form.fps" class="render-form__input" min="1" max="60" required />
      </label>

      <label class="render-form__label">
        Resolution
        <select v-model="form.resolution" class="render-form__input" required>
          <option value="1920x1080">1920x1080</option>
          <option value="3840x2160">3840x2160</option>
          <option value="1280x720">1280x720</option>
        </select>
      </label>
    </div>

    <button type="submit" class="render-form__submit" :disabled="!canSubmit">
      Submit Render
    </button>
  </form>
</template>

<script setup>
import { reactive, computed, watch, onMounted } from 'vue'

const props = defineProps({
  cameras: { type: Object, default: () => ({}) },
  initialValues: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['submit'])

const form = reactive({
  camera: '',
  date_from: '',
  date_to: '',
  time_from: '',
  time_to: '',
  fps: 24,
  resolution: '1920x1080',
})

const cameraNames = computed(() => {
  if (!props.cameras) return []
  return Object.keys(props.cameras).sort()
})

const canSubmit = computed(() => {
  return form.camera && form.date_from && form.date_to
})

function applyInitial(vals) {
  if (!vals) return
  if (vals.camera) form.camera = vals.camera
  if (vals.date_from) form.date_from = vals.date_from
  if (vals.date_to) form.date_to = vals.date_to
  if (vals.time_from) form.time_from = vals.time_from
  if (vals.time_to) form.time_to = vals.time_to
  if (vals.fps) form.fps = Number(vals.fps)
  if (vals.resolution) form.resolution = vals.resolution
}

function handleSubmit() {
  const data = { ...form }
  if (!data.time_from) delete data.time_from
  if (!data.time_to) delete data.time_to
  emit('submit', data)
}

onMounted(() => {
  applyInitial(props.initialValues)
})

watch(() => props.initialValues, (v) => {
  applyInitial(v)
}, { deep: true })
</script>

<style scoped>
.render-form__fields {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 0.9rem;
  margin-bottom: 1.2rem;
}

.render-form__label {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.render-form__input {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 0.45rem 0.6rem;
  border-radius: 6px;
  font-size: 0.85rem;
  font-family: inherit;
}

.render-form__input:focus {
  outline: none;
  border-color: var(--accent-blue);
}

.render-form__input::-webkit-calendar-picker-indicator {
  filter: invert(0.7);
}

.render-form__submit {
  background: var(--accent-blue);
  border: none;
  color: #0f1117;
  padding: 0.55rem 1.5rem;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}

.render-form__submit:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.render-form__submit:not(:disabled):hover {
  opacity: 0.85;
}
</style>
