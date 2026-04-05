<template>
  <div class="compare">
    <header class="compare__header">
      <h1 class="compare__title">Compare</h1>
    </header>

    <!-- Camera selector -->
    <section class="compare__controls">
      <label class="compare__label">
        Camera
        <select v-model="selectedCamera" class="compare__select">
          <option v-for="cam in cameraNames" :key="cam" :value="cam">{{ cam }}</option>
        </select>
      </label>
    </section>

    <!-- Side-by-side pickers -->
    <section class="compare__pickers">
      <!-- Side A (Before) -->
      <div class="compare__picker">
        <label class="compare__picker-label">Before</label>
        <div class="compare__date-row">
          <input type="date" v-model="dateA" class="compare__date-input" />
          <span v-if="dateA && availableDaysA !== null" class="compare__avail"
                :class="availableDaysA === 0 ? 'compare__avail--none' : ''">
            {{ availableDaysA }} day{{ availableDaysA !== 1 ? 's' : '' }} in {{ monthOf(dateA) }}
          </span>
        </div>
        <div class="compare__strip-wrap" v-if="capturesA.length">
          <div class="compare__strip" ref="stripAEl">
            <div
              v-for="cap in capturesA"
              :key="cap.id"
              class="compare__strip-item"
              :class="{ 'compare__strip-item--selected': selectedA?.id === cap.id }"
              @click="selectedA = cap"
            >
              <img :src="cap.thumbnail_url" class="compare__strip-thumb" :alt="formatTime(cap.captured_at)" loading="lazy" />
              <span class="compare__strip-time">{{ formatTime(cap.captured_at) }}</span>
            </div>
          </div>
        </div>
        <div class="compare__selected-info" v-if="selectedA">
          {{ formatDate(selectedA.captured_at) }} at <strong>{{ formatTime(selectedA.captured_at) }}</strong>
        </div>
        <div class="compare__empty" v-else-if="dateA && !loadingA && !capturesA.length">
          No captures on this date
        </div>
        <div class="compare__empty" v-else-if="loadingA">Loading...</div>
      </div>

      <!-- Side B (After) -->
      <div class="compare__picker">
        <label class="compare__picker-label">After</label>
        <div class="compare__date-row">
          <input type="date" v-model="dateB" class="compare__date-input" />
          <span v-if="dateB && availableDaysB !== null" class="compare__avail"
                :class="availableDaysB === 0 ? 'compare__avail--none' : ''">
            {{ availableDaysB }} day{{ availableDaysB !== 1 ? 's' : '' }} in {{ monthOf(dateB) }}
          </span>
        </div>
        <div class="compare__strip-wrap" v-if="capturesB.length">
          <div class="compare__strip" ref="stripBEl">
            <div
              v-for="cap in capturesB"
              :key="cap.id"
              class="compare__strip-item"
              :class="{ 'compare__strip-item--selected': selectedB?.id === cap.id }"
              @click="selectedB = cap"
            >
              <img :src="cap.thumbnail_url" class="compare__strip-thumb" :alt="formatTime(cap.captured_at)" loading="lazy" />
              <span class="compare__strip-time">{{ formatTime(cap.captured_at) }}</span>
            </div>
          </div>
        </div>
        <div class="compare__selected-info" v-if="selectedB">
          {{ formatDate(selectedB.captured_at) }} at <strong>{{ formatTime(selectedB.captured_at) }}</strong>
        </div>
        <div class="compare__empty" v-else-if="dateB && !loadingB && !capturesB.length">
          No captures on this date
        </div>
        <div class="compare__empty" v-else-if="loadingB">Loading...</div>
      </div>
    </section>

    <!-- Slider comparison -->
    <section class="compare__slider" v-if="selectedA && selectedB">
      <ImageCompare
        :imageA="selectedA.image_url"
        :imageB="selectedB.image_url"
        :labelA="formatDate(selectedA.captured_at) + ' ' + formatTime(selectedA.captured_at)"
        :labelB="formatDate(selectedB.captured_at) + ' ' + formatTime(selectedB.captured_at)"
      />
    </section>

    <div v-else-if="dateA && dateB && !loadingA && !loadingB" class="compare__hint">
      Click a thumbnail from each date to compare
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { api } from '../api'
import ImageCompare from '../components/ImageCompare.vue'

defineProps({
  access: { type: String, default: 'local' },
})

// State
const cameras = ref({})
const selectedCamera = ref('')
const dateA = ref('')
const dateB = ref('')
const capturesA = ref([])
const capturesB = ref([])
const selectedA = ref(null)
const selectedB = ref(null)
const loadingA = ref(false)
const loadingB = ref(false)
const availableDaysA = ref(null)
const availableDaysB = ref(null)
const stripAEl = ref(null)
const stripBEl = ref(null)

function scrollStripToSelected(stripEl, captures, selected) {
  if (!stripEl || !selected) return
  const idx = captures.findIndex(c => c.id === selected.id)
  if (idx < 0) return
  const item = stripEl.children[idx]
  if (!item) return
  const stripRect = stripEl.getBoundingClientRect()
  const itemRect = item.getBoundingClientRect()
  const scrollTo = item.offsetLeft - stripRect.width / 2 + itemRect.width / 2
  stripEl.scrollTo({ left: scrollTo, behavior: 'smooth' })
}

// Derived
const cameraNames = computed(() => {
  if (!cameras.value) return []
  return Object.keys(cameras.value).sort()
})

// Find the capture closest to midday (sensible default)
function findMidday(captures) {
  if (!captures.length) return null
  const targetMinutes = 12 * 60
  let best = null
  let bestDiff = Infinity
  for (const cap of captures) {
    try {
      const d = new Date(cap.captured_at)
      const diff = Math.abs(d.getHours() * 60 + d.getMinutes() - targetMinutes)
      if (diff < bestDiff) { bestDiff = diff; best = cap }
    } catch { continue }
  }
  return best
}

function formatTime(isoStr) {
  try {
    return new Date(isoStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch { return isoStr }
}

function formatDate(isoStr) {
  try {
    return new Date(isoStr).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' })
  } catch { return isoStr }
}

function monthOf(dateStr) {
  try {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString([], { month: 'short', year: 'numeric' })
  } catch { return dateStr }
}

function getMonth(dateStr) {
  if (!dateStr) return null
  return dateStr.substring(0, 7)
}

function yesterdayStr() {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0')
}

function todayStr() {
  const d = new Date()
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0')
}

// Data fetching
async function fetchCaptures(date) {
  if (!date || !selectedCamera.value) return []
  try {
    const res = await api.getCaptures({ date, camera: selectedCamera.value, per_page: 1000, sort: 'asc' })
    return res.captures ?? []
  } catch { return [] }
}

async function fetchAvailableDays(date) {
  const month = getMonth(date)
  if (!month || !selectedCamera.value) return null
  try {
    const res = await api.getCaptureDates({ camera: selectedCamera.value, month })
    return res.dates?.length ?? 0
  } catch { return null }
}

async function fetchA() {
  if (!dateA.value) return
  loadingA.value = true
  capturesA.value = await fetchCaptures(dateA.value)
  selectedA.value = findMidday(capturesA.value)
  loadingA.value = false
  await nextTick()
  scrollStripToSelected(stripAEl.value, capturesA.value, selectedA.value)
  availableDaysA.value = await fetchAvailableDays(dateA.value)
}

async function fetchB() {
  if (!dateB.value) return
  loadingB.value = true
  capturesB.value = await fetchCaptures(dateB.value)
  selectedB.value = findMidday(capturesB.value)
  loadingB.value = false
  await nextTick()
  scrollStripToSelected(stripBEl.value, capturesB.value, selectedB.value)
  availableDaysB.value = await fetchAvailableDays(dateB.value)
}

async function fetchCameras() {
  try {
    const res = await api.getCameras()
    cameras.value = res.cameras || {}
    if (cameraNames.value.length && !selectedCamera.value) {
      selectedCamera.value = cameraNames.value[0]
    }
  } catch { /* Non-critical */ }
}

// Watchers
watch([selectedCamera, dateA], fetchA)
watch([selectedCamera, dateB], fetchB)
watch(selectedCamera, () => {
  capturesA.value = []
  capturesB.value = []
  selectedA.value = null
  selectedB.value = null
  availableDaysA.value = null
  availableDaysB.value = null
})

onMounted(() => {
  fetchCameras()
  dateA.value = yesterdayStr()
  dateB.value = todayStr()
})
</script>

<style scoped>
.compare {
  color: var(--text-primary);
}

.compare__header {
  margin-bottom: 1.2rem;
}

.compare__title {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
}

.compare__controls {
  margin-bottom: 1.2rem;
}

.compare__label {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.compare__select,
.compare__date-input {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 0.45rem 0.6rem;
  border-radius: var(--radius-sm, 4px);
  font-size: 0.9rem;
}

.compare__pickers {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.compare__picker {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.compare__picker-label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.compare__date-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.compare__avail {
  font-size: 0.75rem;
  color: var(--accent-green, #4ade80);
}

.compare__avail--none {
  color: var(--accent-amber, #fbbf24);
}

/* Thumbnail strip — single scrollable row */
.compare__strip-wrap {
  border-radius: var(--radius-sm, 4px);
  background: var(--bg-card);
  border: 1px solid var(--border);
  padding: 0.25rem;
  overflow: hidden;
}

.compare__strip {
  display: flex;
  flex-wrap: nowrap;
  gap: 0.25rem;
  overflow-x: auto;
  overflow-y: hidden;
  max-height: 100px;
  scrollbar-width: thin;
  scrollbar-color: var(--accent-green, #4ade80) var(--bg-card);
}

.compare__strip::-webkit-scrollbar {
  height: 6px;
}

.compare__strip::-webkit-scrollbar-track {
  background: var(--bg-card);
  border-radius: 3px;
}

.compare__strip::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}

.compare__strip-item {
  flex: 0 0 80px;
  cursor: pointer;
  border: 2px solid transparent;
  border-radius: 3px;
  overflow: hidden;
  background: var(--bg-card);
  transition: border-color 0.15s;
}

.compare__strip-item:hover {
  border-color: var(--text-secondary);
}

.compare__strip-item--selected {
  border-color: var(--accent-green, #4ade80);
}

.compare__strip-thumb {
  width: 100%;
  aspect-ratio: 16/9;
  object-fit: cover;
  display: block;
}

.compare__strip-time {
  display: block;
  text-align: center;
  font-size: 0.6rem;
  color: var(--text-secondary);
  padding: 0.1rem 0;
  line-height: 1;
}

/* Selected info line */
.compare__selected-info {
  font-size: 0.8rem;
  color: var(--text-secondary);
  padding: 0.25rem 0;
}

.compare__selected-info strong {
  color: var(--accent-green, #4ade80);
  font-family: var(--font-mono, monospace);
}

.compare__empty {
  padding: 1.5rem 1rem;
  color: var(--text-secondary);
  font-size: 0.85rem;
  text-align: center;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius, 8px);
}

.compare__slider {
  margin-top: 0.5rem;
}

.compare__hint {
  text-align: center;
  color: var(--text-secondary);
  padding: 2rem;
  font-size: 0.9rem;
}
</style>
