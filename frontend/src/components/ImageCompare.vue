<template>
  <div class="image-compare" ref="container" @pointermove="onMove" @pointerup="onUp" @pointerleave="onUp">
    <img :src="imageB" class="image-compare__img image-compare__img--base" alt="After" @load="loadedB = true" />
    <div class="image-compare__overlay" :style="{ clipPath: `inset(0 ${100 - position}% 0 0)` }">
      <img :src="imageA" class="image-compare__img" alt="Before" @load="loadedA = true" />
    </div>
    <div
      class="image-compare__handle"
      :style="{ left: position + '%' }"
      @pointerdown.prevent="onDown"
    >
      <div class="image-compare__handle-line"></div>
      <div class="image-compare__handle-grip">
        <span>◀ ▶</span>
      </div>
    </div>
    <div class="image-compare__labels" v-if="labelA || labelB">
      <span class="image-compare__label image-compare__label--a">{{ labelA }}</span>
      <span class="image-compare__label image-compare__label--b">{{ labelB }}</span>
    </div>
    <div class="image-compare__loading" v-if="!loadedA || !loadedB">Loading images...</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  imageA: { type: String, required: true },
  imageB: { type: String, required: true },
  labelA: { type: String, default: '' },
  labelB: { type: String, default: '' },
})

const container = ref(null)
const position = ref(50)
const dragging = ref(false)
const loadedA = ref(false)
const loadedB = ref(false)

function onDown() {
  dragging.value = true
}

function onMove(e) {
  if (!dragging.value || !container.value) return
  const rect = container.value.getBoundingClientRect()
  const pct = ((e.clientX - rect.left) / rect.width) * 100
  position.value = Math.max(0, Math.min(100, pct))
}

function onUp() {
  dragging.value = false
}
</script>

<style scoped>
.image-compare {
  position: relative;
  width: 100%;
  overflow: hidden;
  border-radius: var(--radius, 8px);
  border: 1px solid var(--border, #2a2d3a);
  background: var(--bg-card, #1a1d27);
  touch-action: none;
  user-select: none;
  cursor: ew-resize;
}

.image-compare__img {
  display: block;
  width: 100%;
  height: auto;
}

.image-compare__overlay {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.image-compare__overlay .image-compare__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-compare__handle {
  position: absolute;
  top: 0;
  bottom: 0;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 2;
  cursor: ew-resize;
}

.image-compare__handle-line {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--accent-green, #4ade80);
  box-shadow: 0 0 6px rgba(74, 222, 128, 0.4);
}

.image-compare__handle-grip {
  position: relative;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--accent-green, #4ade80);
  color: var(--bg-primary, #0f1117);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.65rem;
  font-weight: bold;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
  letter-spacing: 2px;
}

.image-compare__labels {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  justify-content: space-between;
  padding: 0.5rem 0.75rem;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.6));
  pointer-events: none;
}

.image-compare__label {
  font-size: 0.8rem;
  color: #fff;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
}

.image-compare__loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary, #8b8d98);
  font-size: 0.9rem;
  background: var(--bg-card, #1a1d27);
}
</style>
