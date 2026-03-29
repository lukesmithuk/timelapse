<template>
  <div class="gallery">
    <header class="gallery__header">
      <h1 class="gallery__title">Gallery</h1>
      <div class="gallery__mode-toggle">
        <button
          class="gallery__mode-btn"
          :class="{ 'gallery__mode-btn--active': mode === 'date' }"
          @click="mode = 'date'"
        >By Date</button>
        <button
          class="gallery__mode-btn"
          :class="{ 'gallery__mode-btn--active': mode === 'year' }"
          @click="mode = 'year'"
        >Through Year</button>
      </div>
    </header>

    <!-- By Date mode -->
    <section v-if="mode === 'date'" class="gallery__controls">
      <div class="gallery__date-nav">
        <button class="gallery__arrow-btn" @click="prevDay" aria-label="Previous day">&#8249;</button>
        <input type="date" v-model="selectedDate" class="gallery__date-input" />
        <button class="gallery__arrow-btn" @click="nextDay" aria-label="Next day">&#8250;</button>
      </div>
      <div class="gallery__camera-filters">
        <button
          class="gallery__filter-btn"
          :class="{ 'gallery__filter-btn--active': selectedCamera === null }"
          @click="selectedCamera = null"
        >All</button>
        <button
          v-for="cam in cameraNames"
          :key="cam"
          class="gallery__filter-btn"
          :class="{ 'gallery__filter-btn--active': selectedCamera === cam }"
          @click="selectedCamera = cam"
        >{{ cam }}</button>
      </div>
    </section>

    <!-- Through Year mode -->
    <section v-if="mode === 'year'" class="gallery__controls">
      <div class="gallery__year-controls">
        <label class="gallery__label">
          Time
          <input type="time" v-model="selectedTime" class="gallery__time-input" />
        </label>
        <label class="gallery__label">
          Camera
          <select v-model="yearCamera" class="gallery__select">
            <option v-for="cam in cameraNames" :key="cam" :value="cam">{{ cam }}</option>
          </select>
        </label>
        <label class="gallery__label">
          Month
          <input type="month" v-model="selectedMonth" class="gallery__month-input" />
        </label>
      </div>
      <button
        class="gallery__render-btn"
        :disabled="!captures.length"
        @click="goToRender"
      >Render as timelapse</button>
    </section>

    <!-- Count + Sort -->
    <div class="gallery__toolbar" v-if="!loading && captures.length">
      <p class="gallery__count">
        Showing {{ captures.length }} capture{{ captures.length !== 1 ? 's' : '' }}
      </p>
      <button class="gallery__sort-btn" @click="sortAsc = !sortAsc" :title="sortAsc ? 'Oldest first' : 'Newest first'">
        {{ sortAsc ? '↑ Oldest first' : '↓ Newest first' }}
      </button>
    </div>

    <!-- Grid -->
    <ImageGrid
      :captures="sortedCaptures"
      :loading="loading"
      @click="openViewer"
    />

    <!-- Error -->
    <div v-if="error" class="gallery__error">{{ error }}</div>

    <!-- Lightbox -->
    <ImageViewer
      v-if="viewerOpen"
      :captures="sortedCaptures"
      :current-index="viewerIndex"
      @close="viewerOpen = false"
      @navigate="viewerIndex = $event"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import ImageGrid from '../components/ImageGrid.vue'
import ImageViewer from '../components/ImageViewer.vue'

const router = useRouter()

// State
const mode = ref('date')
const selectedDate = ref(todayStr())
const selectedCamera = ref(null)
const selectedTime = ref('12:00')
const selectedMonth = ref(currentMonthStr())
const cameras = ref({})
const captures = ref([])
const loading = ref(false)
const error = ref(null)
const sortAsc = ref(true)
const viewerOpen = ref(false)
const viewerIndex = ref(0)

// Derived
const cameraNames = computed(() => {
  if (!cameras.value?.cameras) return []
  return Object.keys(cameras.value.cameras).sort()
})

const yearCamera = computed({
  get: () => {
    if (cameraNames.value.length && !cameraNames.value.includes(selectedCamera.value)) {
      return cameraNames.value[0]
    }
    return selectedCamera.value ?? (cameraNames.value[0] || null)
  },
  set: (v) => { selectedCamera.value = v },
})

const sortedCaptures = computed(() => {
  if (sortAsc.value) return captures.value
  return [...captures.value].reverse()
})

// Close lightbox when sort order changes to avoid stale index
watch(sortAsc, () => { viewerOpen.value = false })

// Helpers
function todayStr() {
  const d = new Date()
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0')
}

function currentMonthStr() {
  const d = new Date()
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
}

function prevDay() {
  const d = new Date(selectedDate.value + 'T00:00:00')
  d.setDate(d.getDate() - 1)
  selectedDate.value = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0')
}

function nextDay() {
  const d = new Date(selectedDate.value + 'T00:00:00')
  d.setDate(d.getDate() + 1)
  selectedDate.value = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0')
}

function openViewer(_capture, index) {
  viewerIndex.value = index
  viewerOpen.value = true
}

function goToRender() {
  router.push({
    name: 'render',
    query: {
      camera: yearCamera.value,
      time: selectedTime.value,
      month: selectedMonth.value,
    },
  })
}

// Data fetching
async function fetchCaptures() {
  loading.value = true
  error.value = null
  captures.value = []
  try {
    if (mode.value === 'date') {
      const params = {
        date: selectedDate.value,
        camera: selectedCamera.value,
        page: 1,
        per_page: 200,
      }
      const res = await api.getCaptures(params)
      captures.value = res.captures ?? []
    } else {
      const params = {
        camera: yearCamera.value,
        time: selectedTime.value,
        month: selectedMonth.value,
      }
      const res = await api.getCapturesByTime(params)
      captures.value = res.captures ?? []
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function fetchCameras() {
  try {
    cameras.value = await api.getCameras()
  } catch {
    // Non-critical
  }
}

// Watchers
watch([mode, selectedDate, selectedCamera], fetchCaptures)
watch([selectedTime, selectedMonth], () => {
  if (mode.value === 'year') fetchCaptures()
})
watch(yearCamera, () => {
  if (mode.value === 'year') fetchCaptures()
})

onMounted(() => {
  fetchCameras()
  fetchCaptures()
})
</script>

<style scoped>
.gallery {
  /* CSS variables inherited from global style.css */

  max-width: 1100px;
  margin: 0 auto;
  padding: 1.5rem 1rem;
  color: var(--text-primary);
}

.gallery__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.8rem;
  margin-bottom: 1.2rem;
}

.gallery__title {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
}

.gallery__mode-toggle {
  display: flex;
  gap: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.gallery__mode-btn {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 0.4rem 1rem;
  font-size: 0.8rem;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.gallery__mode-btn--active {
  background: var(--accent-blue);
  color: #0f1117;
  font-weight: 600;
}

.gallery__mode-btn:not(.gallery__mode-btn--active):hover {
  background: var(--bg-card-hover);
}

.gallery__controls {
  margin-bottom: 1rem;
}

.gallery__date-nav {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.8rem;
}

.gallery__arrow-btn {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-primary);
  font-size: 1.3rem;
  line-height: 1;
  padding: 0.3rem 0.7rem;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}

.gallery__arrow-btn:hover {
  background: var(--bg-card-hover);
}

.gallery__date-input,
.gallery__time-input,
.gallery__month-input,
.gallery__select {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 0.4rem 0.6rem;
  border-radius: 6px;
  font-size: 0.85rem;
  font-family: inherit;
}

.gallery__date-input::-webkit-calendar-picker-indicator,
.gallery__time-input::-webkit-calendar-picker-indicator,
.gallery__month-input::-webkit-calendar-picker-indicator {
  filter: invert(0.7);
}

.gallery__camera-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.gallery__filter-btn {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 0.3rem 0.8rem;
  border-radius: 6px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.gallery__filter-btn--active {
  background: var(--accent-green);
  color: #0f1117;
  border-color: var(--accent-green);
  font-weight: 600;
}

.gallery__filter-btn:not(.gallery__filter-btn--active):hover {
  background: var(--bg-card-hover);
  color: var(--text-primary);
}

.gallery__year-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: flex-end;
  margin-bottom: 0.8rem;
}

.gallery__label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.gallery__render-btn {
  background: var(--accent-blue);
  border: none;
  color: #0f1117;
  padding: 0.5rem 1.2rem;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}

.gallery__render-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.gallery__render-btn:not(:disabled):hover {
  opacity: 0.85;
}

.gallery__toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.8rem;
}

.gallery__count {
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin: 0;
}

.gallery__sort-btn {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 0.3rem 0.7rem;
  border-radius: var(--radius-sm, 4px);
  cursor: pointer;
  font-size: 0.8rem;
}

.gallery__sort-btn:hover {
  color: var(--text-primary);
  border-color: var(--accent-blue);
}

.gallery__error {
  text-align: center;
  color: var(--accent-amber);
  padding: 1rem;
  background: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.2);
  border-radius: 8px;
  margin-top: 1rem;
  font-size: 0.85rem;
}

@media (max-width: 500px) {
  .gallery__header {
    flex-direction: column;
    align-items: flex-start;
  }

  .gallery__year-controls {
    flex-direction: column;
  }
}
</style>
