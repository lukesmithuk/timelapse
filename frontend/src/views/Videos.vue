<template>
  <div class="videos">
    <header class="videos__header">
      <h1 class="videos__title">Videos</h1>
      <div class="videos__controls">
        <div class="videos__toggle">
          <button
            v-for="opt in typeOptions"
            :key="opt.value"
            class="videos__toggle-btn"
            :class="{ 'videos__toggle-btn--active': typeFilter === opt.value }"
            @click="typeFilter = opt.value"
          >{{ opt.label }}</button>
        </div>
        <select v-model="cameraFilter" class="videos__select">
          <option :value="null">All cameras</option>
          <option v-for="cam in cameraNames" :key="cam" :value="cam">{{ cam }}</option>
        </select>
      </div>
    </header>

    <div v-if="loading && !jobs.length" class="videos__loading">Loading...</div>

    <div v-if="completedJobs.length" class="videos__grid">
      <VideoCard v-for="job in completedJobs" :key="job.id" :job="job" />
    </div>

    <div v-if="!loading && !completedJobs.length && !failedJobs.length" class="videos__empty">
      No videos found.
    </div>

    <section v-if="failedJobs.length" class="videos__failed-section">
      <h2 class="videos__section-title">Failed Renders</h2>
      <VideoCard v-for="job in failedJobs" :key="job.id" :job="job" />
    </section>

    <div v-if="error" class="videos__error">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import VideoCard from '../components/VideoCard.vue'

const typeOptions = [
  { label: 'All', value: null },
  { label: 'Daily', value: 'daily' },
  { label: 'Custom', value: 'custom' },
]

const typeFilter = ref(null)
const cameraFilter = ref(null)
const jobs = ref([])
const cameras = ref({})
const loading = ref(false)
const error = ref(null)

const cameraNames = computed(() => {
  if (!cameras.value?.cameras) return []
  return Object.keys(cameras.value.cameras).sort()
})

const filteredJobs = computed(() => {
  let list = [...jobs.value]
  if (typeFilter.value) {
    list = list.filter((j) => j.job_type === typeFilter.value)
  }
  if (cameraFilter.value) {
    list = list.filter((j) => j.camera === cameraFilter.value)
  }
  list.sort((a, b) => {
    const ta = new Date(a.created_at || 0).getTime()
    const tb = new Date(b.created_at || 0).getTime()
    return tb - ta
  })
  return list
})

const completedJobs = computed(() => filteredJobs.value.filter((j) => j.status === 'done'))
const failedJobs = computed(() => filteredJobs.value.filter((j) => j.status === 'failed'))

async function fetchJobs() {
  loading.value = true
  error.value = null
  try {
    // Fetch done and failed jobs
    const [doneRes, failedRes] = await Promise.all([
      api.getRenders({ status: 'done' }),
      api.getRenders({ status: 'failed' }),
    ])
    jobs.value = [...(doneRes.jobs || []), ...(failedRes.jobs || [])]
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

onMounted(() => {
  fetchCameras()
  fetchJobs()
})
</script>

<style scoped>
.videos {
  /* CSS variables inherited from global style.css */

  max-width: 1100px;
  margin: 0 auto;
  padding: 1.5rem 1rem;
  color: var(--text-primary);
}

.videos__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.8rem;
  margin-bottom: 1.5rem;
}

.videos__title {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
}

.videos__controls {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  flex-wrap: wrap;
}

.videos__toggle {
  display: flex;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.videos__toggle-btn {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 0.4rem 0.9rem;
  font-size: 0.8rem;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.videos__toggle-btn--active {
  background: var(--accent-blue);
  color: #0f1117;
  font-weight: 600;
}

.videos__toggle-btn:not(.videos__toggle-btn--active):hover {
  background: var(--bg-card-hover);
}

.videos__select {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 0.4rem 0.6rem;
  border-radius: 6px;
  font-size: 0.85rem;
  font-family: inherit;
}

.videos__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.videos__failed-section {
  margin-top: 1.5rem;
}

.videos__section-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 0.8rem 0;
}

.videos__loading {
  text-align: center;
  color: var(--text-secondary);
  padding: 3rem 0;
  font-size: 0.9rem;
}

.videos__empty {
  text-align: center;
  color: var(--text-secondary);
  padding: 3rem 0;
  font-size: 0.9rem;
}

.videos__error {
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
  .videos__header {
    flex-direction: column;
    align-items: flex-start;
  }

  .videos__grid {
    grid-template-columns: 1fr;
  }
}
</style>
