<template>
  <Teleport to="body">
    <div class="viewer-backdrop" @click.self="$emit('close')">
      <button class="viewer__close" @click="$emit('close')" aria-label="Close">&times;</button>

      <button
        v-if="currentIndex > 0"
        class="viewer__nav viewer__nav--prev"
        @click.stop="$emit('navigate', currentIndex - 1)"
        aria-label="Previous"
      >&#8249;</button>

      <div class="viewer__content" @click.stop>
        <img
          v-if="current"
          :src="current.image_url"
          :alt="current.camera + ' ' + current.captured_at"
          class="viewer__img"
        />
        <div v-if="current" class="viewer__info">
          <span class="viewer__camera">{{ current.camera }}</span>
          <span class="viewer__time">{{ formatTimestamp(current.captured_at) }}</span>
        </div>
        <WeatherDetail
          v-if="showWeather && captureWeather"
          :weather="captureWeather"
          class="viewer__weather"
        />
      </div>

      <button
        v-if="currentIndex < captures.length - 1"
        class="viewer__nav viewer__nav--next"
        @click.stop="$emit('navigate', currentIndex + 1)"
        aria-label="Next"
      >&#8250;</button>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { api } from '../api'
import WeatherDetail from './WeatherDetail.vue'

const props = defineProps({
  captures: { type: Array, required: true },
  currentIndex: { type: Number, required: true },
})

const emit = defineEmits(['close', 'navigate'])

const current = computed(() => props.captures[props.currentIndex] ?? null)

const showWeather = ref(localStorage.getItem('timelapse-show-weather') === 'true')
const captureWeather = ref(null)

async function fetchCaptureWeather() {
  if (!showWeather.value || !current.value?.captured_at) {
    captureWeather.value = null
    return
  }
  try {
    captureWeather.value = await api.getWeatherForCapture({ captured_at: current.value.captured_at })
  } catch {
    captureWeather.value = null
  }
}

watch(() => current.value?.captured_at, fetchCaptureWeather, { immediate: true })

function formatTimestamp(iso) {
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    return d.toLocaleString([], {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function onKeydown(e) {
  if (e.key === 'Escape') {
    emit('close')
  } else if (e.key === 'ArrowLeft' && props.currentIndex > 0) {
    emit('navigate', props.currentIndex - 1)
  } else if (e.key === 'ArrowRight' && props.currentIndex < props.captures.length - 1) {
    emit('navigate', props.currentIndex + 1)
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.viewer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.88);
  display: flex;
  align-items: center;
  justify-content: center;
}

.viewer__close {
  position: absolute;
  top: 0.8rem;
  right: 1rem;
  background: none;
  border: none;
  color: #e4e4e7;
  font-size: 2rem;
  cursor: pointer;
  line-height: 1;
  padding: 0.3rem 0.6rem;
  border-radius: 6px;
  transition: background 0.15s;
  z-index: 10;
}

.viewer__close:hover {
  background: rgba(255, 255, 255, 0.1);
}

.viewer__nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(255, 255, 255, 0.07);
  border: none;
  color: #e4e4e7;
  font-size: 2.5rem;
  cursor: pointer;
  padding: 0.6rem 1rem;
  border-radius: 8px;
  line-height: 1;
  transition: background 0.15s;
  z-index: 10;
}

.viewer__nav:hover {
  background: rgba(255, 255, 255, 0.15);
}

.viewer__nav--prev {
  left: 0.8rem;
}

.viewer__nav--next {
  right: 0.8rem;
}

.viewer__content {
  display: flex;
  flex-direction: column;
  align-items: center;
  max-width: 90vw;
  max-height: 90vh;
}

.viewer__img {
  max-width: 90vw;
  max-height: 80vh;
  object-fit: contain;
  border-radius: 6px;
}

.viewer__info {
  display: flex;
  gap: 1rem;
  align-items: center;
  margin-top: 0.8rem;
  font-size: 0.85rem;
}

.viewer__camera {
  color: #4ade80;
  font-weight: 600;
}

.viewer__time {
  color: #8b8d98;
}

.viewer__weather {
  margin-top: 0.5rem;
  max-width: 400px;
}
</style>
