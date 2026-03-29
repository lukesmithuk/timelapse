<template>
  <div class="job-queue">
    <div v-if="!jobs.length" class="job-queue__empty">
      No jobs in queue.
    </div>
    <div
      v-for="job in jobs"
      :key="job.id"
      class="job-queue__item"
      :class="statusClass(job.status)"
    >
      <span class="job-queue__indicator" :class="indicatorClass(job.status)">
        <span v-if="job.status === 'running'" class="job-queue__pulse"></span>
        <span v-else-if="job.status === 'done'" class="job-queue__check">&#10003;</span>
        <span v-else-if="job.status === 'failed'" class="job-queue__x">&#10005;</span>
        <span v-else class="job-queue__dot"></span>
      </span>

      <div class="job-queue__content">
        <div class="job-queue__row">
          <span class="job-queue__status-text">{{ statusLabel(job.status) }}</span>
          <span class="job-queue__camera">{{ job.camera }}</span>
          <span class="job-queue__dates">{{ job.date_from }}{{ job.date_to && job.date_to !== job.date_from ? ' to ' + job.date_to : '' }}</span>
        </div>
        <div class="job-queue__secondary">
          <span v-if="job.status === 'running'">Started {{ timeAgo(job.created_at) }}</span>
          <span v-else-if="job.status === 'pending'">Queued {{ timeAgo(job.created_at) }}</span>
          <span v-else-if="job.status === 'done' && job.completed_at">Completed {{ formatDate(job.completed_at) }}</span>
          <span v-else-if="job.status === 'failed' && job.error" class="job-queue__error">{{ job.error }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  jobs: { type: Array, default: () => [] },
})

function statusLabel(status) {
  const labels = { running: 'Running', pending: 'Pending', done: 'Complete', failed: 'Failed' }
  return labels[status] || status
}

function statusClass(status) {
  return `job-queue__item--${status}`
}

function indicatorClass(status) {
  return `job-queue__indicator--${status}`
}

function timeAgo(iso) {
  if (!iso) return ''
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ago`
}

function formatDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString([], {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}
</script>

<style scoped>
.job-queue__empty {
  color: var(--text-secondary);
  font-size: 0.85rem;
  padding: 1rem 0;
}

.job-queue__item {
  display: flex;
  align-items: flex-start;
  gap: 0.7rem;
  padding: 0.7rem 0.9rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 0.4rem;
}

.job-queue__item--failed {
  border-color: rgba(239, 68, 68, 0.4);
}

.job-queue__indicator {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  margin-top: 0.1rem;
}

.job-queue__pulse {
  display: block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent-green);
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.5); }
  50% { opacity: 0.7; box-shadow: 0 0 0 5px rgba(74, 222, 128, 0); }
}

.job-queue__dot {
  display: block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent-amber);
}

.job-queue__check {
  color: var(--accent-green);
  font-size: 0.85rem;
  font-weight: 700;
}

.job-queue__x {
  color: #ef4444;
  font-size: 0.85rem;
  font-weight: 700;
}

.job-queue__content {
  flex: 1;
  min-width: 0;
}

.job-queue__row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  font-size: 0.85rem;
}

.job-queue__status-text {
  font-weight: 600;
  color: var(--text-primary);
}

.job-queue__camera {
  color: var(--accent-blue);
  font-size: 0.8rem;
}

.job-queue__dates {
  color: var(--text-secondary);
  font-size: 0.78rem;
}

.job-queue__secondary {
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-top: 0.15rem;
}

.job-queue__error {
  color: #ef4444;
}
</style>
