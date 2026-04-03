<template>
  <div class="render">
    <header class="render__header">
      <h1 class="render__title">Render</h1>
    </header>

    <div v-if="access === 'viewer'" class="render__restricted">
      Render submission is only available on the local network or for admin users.
    </div>

    <section v-else class="render__form-section">
      <h2 class="render__section-title">New Render</h2>
      <RenderForm
        :cameras="cameras"
        :initial-values="initialValues"
        @submit="handleSubmit"
      />
      <div v-if="submitMessage" class="render__submit-msg" :class="submitError ? 'render__submit-msg--error' : 'render__submit-msg--success'">
        {{ submitMessage }}
      </div>
    </section>

    <section class="render__queue-section">
      <h2 class="render__section-title">Job Queue</h2>
      <JobQueue :jobs="queueJobs" />
    </section>

    <div v-if="error" class="render__error">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import RenderForm from '../components/RenderForm.vue'
import JobQueue from '../components/JobQueue.vue'

const props = defineProps({
  access: { type: String, default: 'local' },
})

const POLL_INTERVAL = 15000

const route = useRoute()

const cameras = ref({})
const allJobs = ref([])
const error = ref(null)
const submitMessage = ref(null)
const submitError = ref(false)
let pollTimer = null

const initialValues = computed(() => {
  const q = route.query
  const vals = {}
  if (q.camera) vals.camera = q.camera
  if (q.date_from) vals.date_from = q.date_from
  if (q.date_to) vals.date_to = q.date_to
  if (q.time_from) vals.time_from = q.time_from
  if (q.time_to) vals.time_to = q.time_to
  // Support the Gallery's month/time query format
  if (q.month && !q.date_from) {
    const [year, month] = q.month.split('-')
    vals.date_from = `${year}-${month}-01`
    const lastDay = new Date(Number(year), Number(month), 0).getDate()
    vals.date_to = `${year}-${month}-${String(lastDay).padStart(2, '0')}`
  }
  if (q.time && !q.time_from) {
    vals.time_from = q.time
    // Default a 2-hour window around the selected time
    const [h, m] = q.time.split(':').map(Number)
    const endH = Math.min(h + 2, 23)
    vals.time_to = `${String(endH).padStart(2, '0')}:${String(m).padStart(2, '0')}`
  }
  return vals
})

const queueJobs = computed(() => {
  return [...allJobs.value].sort((a, b) => {
    const order = { running: 0, pending: 1, done: 2, failed: 3 }
    const oa = order[a.status] ?? 4
    const ob = order[b.status] ?? 4
    if (oa !== ob) return oa - ob
    return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
  })
})

async function fetchJobs() {
  try {
    const res = await api.getRenders({})
    allJobs.value = res.jobs || []
  } catch (e) {
    error.value = e.message
  }
}

async function fetchCameras() {
  try {
    const res = await api.getCameras()
    cameras.value = res.cameras || {}
  } catch {
    // Non-critical
  }
}

async function handleSubmit(formData) {
  submitMessage.value = null
  submitError.value = false
  try {
    const res = await api.submitRender(formData)
    submitMessage.value = `Render submitted (job #${res.id})`
    submitError.value = false
    fetchJobs()
  } catch (e) {
    submitMessage.value = `Failed to submit: ${e.message}`
    submitError.value = true
  }
}

onMounted(() => {
  fetchCameras()
  fetchJobs()
  pollTimer = setInterval(fetchJobs, POLL_INTERVAL)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.render {
  /* CSS variables inherited from global style.css */

  max-width: 1100px;
  margin: 0 auto;
  padding: 1.5rem 1rem;
  color: var(--text-primary);
}

.render__restricted {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius, 8px);
  padding: 2rem;
  text-align: center;
  color: var(--text-secondary);
  font-size: 0.95rem;
}

.render__header {
  margin-bottom: 1.5rem;
}

.render__title {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
}

.render__form-section {
  margin-bottom: 2.5rem;
}

.render__queue-section {
  margin-bottom: 2rem;
}

.render__section-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 0.9rem 0;
}

.render__submit-msg {
  margin-top: 0.8rem;
  font-size: 0.85rem;
  padding: 0.5rem 0.8rem;
  border-radius: 6px;
}

.render__submit-msg--success {
  color: var(--accent-green);
  background: rgba(74, 222, 128, 0.08);
  border: 1px solid rgba(74, 222, 128, 0.2);
}

.render__submit-msg--error {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.render__error {
  text-align: center;
  color: var(--accent-amber);
  padding: 1rem;
  background: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.2);
  border-radius: 8px;
  margin-top: 1rem;
  font-size: 0.85rem;
}
</style>
