<template>
  <div class="dashboard">
    <header class="dashboard__header">
      <h1 class="dashboard__title">Dashboard</h1>
      <span v-if="lastRefresh" class="dashboard__refresh">
        Updated {{ lastRefreshFormatted }}
      </span>
    </header>

    <!-- Status Cards -->
    <section class="dashboard__cards">
      <StatusCard
        title="System"
        :value="systemState"
        :subtitle="uptimeText"
        :variant="systemState === 'online' ? 'success' : 'error'"
      />
      <StatusCard
        title="Today's Captures"
        :value="String(totalCapturesToday)"
        :subtitle="`across ${cameraCount} camera${cameraCount !== 1 ? 's' : ''}`"
      />
      <StatusCard
        title="Storage"
        :value="storageText"
        :subtitle="storageSubtitle"
        :variant="storageVariant"
      >
        <div v-if="status?.storage" class="storage-bar">
          <div class="storage-bar__fill" :style="{ width: storagePercent + '%' }" :class="storageBarClass" />
        </div>
      </StatusCard>
      <StatusCard
        title="Capture Window"
        :value="captureWindowText"
        :subtitle="captureWindowActive ? 'Currently active' : 'Inactive'"
        :variant="captureWindowActive ? 'success' : 'default'"
      />
    </section>

    <!-- Camera Previews -->
    <section v-if="cameraNames.length" class="dashboard__section">
      <h2 class="dashboard__section-title">Cameras</h2>
      <div class="dashboard__cameras">
        <CameraPreview
          v-for="cam in cameraNames"
          :key="cam"
          :name="cam"
          :thumbnail-url="latestCaptures[cam]?.thumbnail_url || null"
          :last-capture="latestCaptures[cam]?.captured_at || status?.cameras?.[cam]?.last_capture || null"
          :today-count="status?.cameras?.[cam]?.today_count ?? 0"
        />
      </div>
    </section>

    <!-- Recent Activity -->
    <section v-if="recentActivity.length" class="dashboard__section">
      <h2 class="dashboard__section-title">Recent Activity</h2>
      <ul class="activity-list">
        <li v-for="(item, i) in recentActivity" :key="i" class="activity-list__item">
          <span class="activity-list__icon" :class="item.type === 'capture' ? 'activity-list__icon--capture' : 'activity-list__icon--render'">
            {{ item.type === 'capture' ? '\u25CB' : '\u25A0' }}
          </span>
          <span class="activity-list__text">{{ item.text }}</span>
          <span class="activity-list__time">{{ item.time }}</span>
        </li>
      </ul>
    </section>

    <!-- Loading / Error -->
    <div v-if="loading && !status" class="dashboard__loading">Loading...</div>
    <div v-if="error" class="dashboard__error">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '../api'
import StatusCard from '../components/StatusCard.vue'
import CameraPreview from '../components/CameraPreview.vue'

const POLL_INTERVAL = 30000

const status = ref(null)
const latestCaptures = ref({})
const cameras = ref({})
const loading = ref(false)
const error = ref(null)
const lastRefresh = ref(null)
let pollTimer = null

// Computed
const systemState = computed(() => status.value?.state ?? '...')

const uptimeText = computed(() => {
  if (!status.value) return ''
  return status.value.uptime ?? ''
})

const totalCapturesToday = computed(() => {
  if (!status.value?.cameras) return 0
  return Object.values(status.value.cameras).reduce((sum, c) => sum + (c.today_count || 0), 0)
})

const cameraNames = computed(() => {
  const fromStatus = status.value?.cameras ? Object.keys(status.value.cameras) : []
  const fromConfig = cameras.value?.cameras ? Object.keys(cameras.value.cameras) : []
  const all = new Set([...fromStatus, ...fromConfig])
  return [...all].sort()
})

const cameraCount = computed(() => cameraNames.value.length)

const storagePercent = computed(() => status.value?.storage?.percent ?? 0)
const storageText = computed(() => {
  const s = status.value?.storage
  if (!s) return '...'
  return `${s.percent}%`
})
const storageSubtitle = computed(() => {
  const s = status.value?.storage
  if (!s) return ''
  return `${s.used_gb?.toFixed(1) ?? '?'} / ${s.total_gb?.toFixed(1) ?? '?'} GB`
})
const storageVariant = computed(() => {
  const p = storagePercent.value
  if (p >= 90) return 'warning'
  if (p >= 0) return 'default'
  return 'default'
})
const storageBarClass = computed(() => {
  const p = storagePercent.value
  if (p >= 90) return 'storage-bar__fill--warning'
  if (p >= 70) return 'storage-bar__fill--caution'
  return ''
})

const captureWindowText = computed(() => {
  const cw = status.value?.window
  if (!cw?.start) return '...'
  const fmt = (iso) => {
    try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }
    catch { return iso }
  }
  return `${fmt(cw.start)} → ${fmt(cw.end)}`
})
const captureWindowActive = computed(() => status.value?.window?.active ?? false)

const lastRefreshFormatted = computed(() => {
  if (!lastRefresh.value) return ''
  return lastRefresh.value.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
})

const recentActivity = computed(() => {
  const items = []
  // Recent captures from latest
  for (const [cam, data] of Object.entries(latestCaptures.value)) {
    if (data?.captured_at) {
      items.push({
        type: 'capture',
        text: `${cam} captured`,
        time: formatTime(data.captured_at),
        sortKey: new Date(data.captured_at).getTime(),
      })
    }
  }
  // Pending renders from status
  if (status.value?.pending_renders) {
    items.push({
      type: 'render',
      text: `${status.value.pending_renders} render${status.value.pending_renders !== 1 ? 's' : ''} pending`,
      time: '',
      sortKey: 0,
    })
  }
  items.sort((a, b) => b.sortKey - a.sortKey)
  return items.slice(0, 8)
})

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

async function fetchAll() {
  loading.value = true
  error.value = null
  try {
    const [statusRes, capturesRes, camerasRes] = await Promise.allSettled([
      api.getStatus(),
      api.getLatestCaptures(),
      api.getCameras(),
    ])
    if (statusRes.status === 'fulfilled') status.value = statusRes.value
    if (capturesRes.status === 'fulfilled') latestCaptures.value = capturesRes.value
    if (camerasRes.status === 'fulfilled') cameras.value = camerasRes.value
    lastRefresh.value = new Date()

    // If all failed, show error
    if (statusRes.status === 'rejected' && capturesRes.status === 'rejected') {
      error.value = 'Unable to reach the timelapse service'
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchAll()
  pollTimer = setInterval(fetchAll, POLL_INTERVAL)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.dashboard {
  /* CSS variables inherited from global style.css */

  max-width: 1100px;
  margin: 0 auto;
  padding: 1.5rem 1rem;
  color: var(--text-primary);
}

.dashboard__header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 1.5rem;
}

.dashboard__title {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
}

.dashboard__refresh {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.dashboard__cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.9rem;
  margin-bottom: 2rem;
}

@media (max-width: 900px) {
  .dashboard__cards {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 500px) {
  .dashboard__cards {
    grid-template-columns: 1fr;
  }
}

.dashboard__section {
  margin-bottom: 2rem;
}

.dashboard__section-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 0.9rem 0;
}

.dashboard__cameras {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 0.9rem;
}

/* Storage bar inside StatusCard slot */
.storage-bar {
  margin-top: 0.6rem;
  height: 5px;
  background: var(--border);
  border-radius: 3px;
  overflow: hidden;
}

.storage-bar__fill {
  height: 100%;
  background: var(--accent-green);
  border-radius: 3px;
  transition: width 0.4s ease;
}

.storage-bar__fill--caution {
  background: var(--accent-amber);
}

.storage-bar__fill--warning {
  background: #ef4444;
}

/* Activity list */
.activity-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.activity-list__item {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.55rem 0.8rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 0.4rem;
  font-size: 0.85rem;
}

.activity-list__icon {
  flex-shrink: 0;
  font-size: 0.7rem;
}

.activity-list__icon--capture {
  color: var(--accent-green);
}

.activity-list__icon--render {
  color: var(--accent-blue);
}

.activity-list__text {
  flex: 1;
  color: var(--text-primary);
}

.activity-list__time {
  color: var(--text-secondary);
  font-size: 0.75rem;
  flex-shrink: 0;
}

.dashboard__loading {
  text-align: center;
  color: var(--text-secondary);
  padding: 3rem 0;
  font-size: 0.9rem;
}

.dashboard__error {
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
