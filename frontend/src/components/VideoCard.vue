<template>
  <div class="video-card" :class="{ 'video-card--failed': job.status === 'failed' }">
    <div v-if="job.status === 'done' && job.video_url" class="video-card__player">
      <video controls preload="metadata" class="video-card__video">
        <source :src="job.video_url" type="video/mp4" />
      </video>
    </div>

    <div class="video-card__body">
      <h3 class="video-card__title">{{ title }}</h3>

      <div class="video-card__meta">
        <span class="video-card__tag" :class="typeClass">{{ job.job_type }}</span>
        <span class="video-card__date">{{ dateRange }}</span>
        <span v-if="job.time_from || job.time_to" class="video-card__time">
          {{ job.time_from || '?' }} &ndash; {{ job.time_to || '?' }}
        </span>
        <span v-if="job.resolution" class="video-card__res">{{ job.resolution }}</span>
        <span v-if="job.fps" class="video-card__fps">{{ job.fps }} fps</span>
      </div>

      <div v-if="job.status === 'done' && job.video_url" class="video-card__actions">
        <a :href="job.video_url" download class="video-card__download">Download</a>
      </div>

      <div v-if="job.status === 'failed' && job.error" class="video-card__error">
        {{ job.error }}
      </div>

      <div class="video-card__timestamp">
        {{ formatDate(job.created_at) }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  job: { type: Object, required: true },
})

const title = computed(() => {
  const cam = props.job.camera || 'Unknown'
  if (props.job.job_type === 'custom' && props.job.date_from !== props.job.date_to) {
    return `${cam} \u2014 ${props.job.date_from} to ${props.job.date_to}`
  }
  return `${cam} \u2014 ${props.job.date_from || '?'}`
})

const dateRange = computed(() => {
  if (props.job.date_from === props.job.date_to || !props.job.date_to) {
    return props.job.date_from || ''
  }
  return `${props.job.date_from} to ${props.job.date_to}`
})

const typeClass = computed(() => {
  return props.job.job_type === 'daily' ? 'video-card__tag--daily' : 'video-card__tag--custom'
})

function formatDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString([], {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}
</script>

<style scoped>
.video-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  transition: border-color 0.15s;
}

.video-card:hover {
  border-color: var(--accent-blue);
}

.video-card--failed {
  border-color: #ef4444;
}

.video-card--failed:hover {
  border-color: #f87171;
}

.video-card__player {
  background: #000;
}

.video-card__video {
  display: block;
  width: 100%;
  max-height: 360px;
  object-fit: contain;
}

.video-card__body {
  padding: 0.9rem 1rem;
}

.video-card__title {
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0 0 0.5rem 0;
  color: var(--text-primary);
}

.video-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-bottom: 0.6rem;
}

.video-card__tag {
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.video-card__tag--daily {
  background: rgba(74, 222, 128, 0.15);
  color: var(--accent-green);
}

.video-card__tag--custom {
  background: rgba(96, 165, 250, 0.15);
  color: var(--accent-blue);
}

.video-card__actions {
  margin-bottom: 0.5rem;
}

.video-card__download {
  display: inline-block;
  font-size: 0.8rem;
  color: var(--accent-blue);
  text-decoration: none;
  padding: 0.3rem 0.8rem;
  border: 1px solid var(--accent-blue);
  border-radius: 5px;
  transition: background 0.15s, color 0.15s;
}

.video-card__download:hover {
  background: var(--accent-blue);
  color: #0f1117;
}

.video-card__error {
  font-size: 0.8rem;
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 6px;
  padding: 0.5rem 0.7rem;
  margin-bottom: 0.5rem;
}

.video-card__timestamp {
  font-size: 0.7rem;
  color: var(--text-secondary);
}
</style>
