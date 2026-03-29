<template>
  <div :class="['status-card', `status-card--${variant}`]">
    <div class="status-card__title">{{ title }}</div>
    <div class="status-card__value">{{ value }}</div>
    <div v-if="subtitle" class="status-card__subtitle">{{ subtitle }}</div>
    <slot />
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  value: { type: String, required: true },
  subtitle: { type: String, default: '' },
  variant: { type: String, default: 'default', validator: v => ['default', 'success', 'warning'].includes(v) },
})
</script>

<style scoped>
.status-card {
  background: var(--bg-card, #1a1d27);
  border: 1px solid var(--border, #2a2d3a);
  border-radius: 10px;
  padding: 1.25rem;
  min-width: 0;
  transition: background 0.15s ease;
}

.status-card:hover {
  background: var(--bg-card-hover, #22253a);
}

.status-card__title {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-secondary, #8b8d98);
  margin-bottom: 0.5rem;
}

.status-card__value {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-primary, #e4e4e7);
  line-height: 1.2;
}

.status-card--success .status-card__value {
  color: var(--accent-green, #4ade80);
}

.status-card--warning .status-card__value {
  color: var(--accent-amber, #fbbf24);
}

.status-card__subtitle {
  font-size: 0.8rem;
  color: var(--text-secondary, #8b8d98);
  margin-top: 0.35rem;
}
</style>
