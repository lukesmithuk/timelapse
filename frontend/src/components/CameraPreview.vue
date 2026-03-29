<template>
  <div class="camera-preview">
    <div class="camera-preview__image-wrap">
      <img
        v-if="thumbnailUrl"
        :src="thumbnailUrl"
        :alt="`Latest capture from ${name}`"
        class="camera-preview__image"
        loading="lazy"
      />
      <div v-else class="camera-preview__placeholder">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="6" width="20" height="14" rx="2" />
          <circle cx="12" cy="13" r="4" />
          <path d="M7 6V4h4v2" />
        </svg>
        <span>No image yet</span>
      </div>
    </div>
    <div class="camera-preview__info">
      <div class="camera-preview__name">{{ name }}</div>
      <div class="camera-preview__stats">
        <span v-if="lastCapture" class="camera-preview__time">{{ formattedTime }}</span>
        <span v-else class="camera-preview__time camera-preview__time--none">No captures</span>
        <span class="camera-preview__count">{{ todayCount }} today</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  name: { type: String, required: true },
  thumbnailUrl: { type: String, default: null },
  lastCapture: { type: String, default: null },
  todayCount: { type: Number, default: 0 },
})

const formattedTime = computed(() => {
  if (!props.lastCapture) return ''
  try {
    const d = new Date(props.lastCapture)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return props.lastCapture
  }
})
</script>

<style scoped>
.camera-preview {
  background: var(--bg-card, #1a1d27);
  border: 1px solid var(--border, #2a2d3a);
  border-radius: 10px;
  overflow: hidden;
  transition: background 0.15s ease;
}

.camera-preview:hover {
  background: var(--bg-card-hover, #22253a);
}

.camera-preview__image-wrap {
  aspect-ratio: 16 / 10;
  background: #12141c;
  overflow: hidden;
}

.camera-preview__image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.camera-preview__placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  color: var(--text-secondary, #8b8d98);
  font-size: 0.8rem;
}

.camera-preview__info {
  padding: 0.9rem 1rem;
}

.camera-preview__name {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary, #e4e4e7);
  margin-bottom: 0.3rem;
}

.camera-preview__stats {
  display: flex;
  justify-content: space-between;
  font-size: 0.8rem;
  color: var(--text-secondary, #8b8d98);
}

.camera-preview__time--none {
  font-style: italic;
  opacity: 0.6;
}

.camera-preview__count {
  color: var(--accent-green, #4ade80);
  font-weight: 500;
}
</style>
