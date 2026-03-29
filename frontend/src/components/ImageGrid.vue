<template>
  <div class="image-grid">
    <!-- Loading skeletons -->
    <template v-if="loading && !captures.length">
      <div v-for="n in 12" :key="'skel-' + n" class="image-grid__cell image-grid__cell--skeleton">
        <div class="image-grid__skeleton-img" />
        <div class="image-grid__skeleton-label" />
      </div>
    </template>

    <!-- Actual thumbnails -->
    <template v-else>
      <div
        v-for="(capture, i) in captures"
        :key="capture.id"
        class="image-grid__cell"
        @click="$emit('click', capture, i)"
      >
        <img
          :src="capture.thumbnail_url"
          :alt="capture.camera + ' ' + capture.captured_at"
          class="image-grid__img"
          loading="lazy"
        />
        <span class="image-grid__label">{{ formatLabel(capture) }}</span>
      </div>
    </template>

    <div v-if="!loading && !captures.length" class="image-grid__empty">
      No captures found
    </div>
  </div>
</template>

<script setup>
defineProps({
  captures: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  labelMode: { type: String, default: 'time' }, // 'time' or 'date'
})

defineEmits(['click'])

function formatLabel(capture) {
  try {
    const d = new Date(capture.captured_at)
    if (isNaN(d.getTime())) return capture.captured_at
    // For 'date' mode we show "1 Mar" style, for 'time' mode "06:00"
    // Parent controls via labelMode but we detect from context:
    // If all captures are from same date, show time; otherwise show date
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return capture.captured_at
  }
}
</script>

<style scoped>
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 0.6rem;
}

@media (min-width: 700px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  }
}

.image-grid__cell {
  position: relative;
  aspect-ratio: 4 / 3;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  background: var(--bg-card, #1a1d27);
  border: 1px solid var(--border, #2a2d3a);
  transition: border-color 0.15s, transform 0.15s;
}

.image-grid__cell:hover {
  border-color: var(--accent-blue, #60a5fa);
  transform: scale(1.02);
}

.image-grid__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.image-grid__label {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 0.25rem 0.5rem;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.7));
  color: #e4e4e7;
  font-size: 0.72rem;
  font-weight: 500;
  text-align: right;
}

/* Skeleton states */
.image-grid__cell--skeleton {
  cursor: default;
  border-color: transparent;
}

.image-grid__cell--skeleton:hover {
  border-color: transparent;
  transform: none;
}

.image-grid__skeleton-img {
  width: 100%;
  height: 100%;
  background: linear-gradient(110deg, #1a1d27 30%, #22253a 50%, #1a1d27 70%);
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.4s ease-in-out infinite;
}

.image-grid__skeleton-label {
  position: absolute;
  bottom: 0.35rem;
  right: 0.5rem;
  width: 2.5rem;
  height: 0.65rem;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.06);
}

@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.image-grid__empty {
  grid-column: 1 / -1;
  text-align: center;
  color: var(--text-secondary, #8b8d98);
  padding: 3rem 0;
  font-size: 0.9rem;
}
</style>
