<script setup>
const props = defineProps({
  conditions: { type: String, default: '' },
  temperature: { type: Number, default: null },
})

function weatherIcon(conditions) {
  if (!conditions) return '\u{1F324}\uFE0F'
  const c = conditions.toLowerCase()
  if (c.includes('clear')) return '\u2600\uFE0F'
  if (c.includes('partly cloudy')) return '\u26C5'
  if (c.includes('overcast') || c.includes('fog')) return '\u2601\uFE0F'
  if (c.includes('rain') || c.includes('drizzle') || c.includes('shower')) return '\u{1F327}\uFE0F'
  if (c.includes('snow')) return '\u2744\uFE0F'
  if (c.includes('thunderstorm')) return '\u26C8\uFE0F'
  return '\u{1F324}\uFE0F'
}
</script>

<template>
  <span class="weather-badge" v-if="temperature !== null">
    <span class="weather-icon">{{ weatherIcon(conditions) }}</span>
    <span class="weather-temp">{{ Math.round(temperature) }}&deg;C</span>
  </span>
</template>

<style scoped>
.weather-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 24px;
  padding: 0 8px;
  background: var(--bg-card, #1a1d27);
  border: 1px solid var(--border, #2a2d3a);
  border-radius: 12px;
  font-size: 12px;
  line-height: 1;
  white-space: nowrap;
}

.weather-icon {
  font-size: 14px;
  line-height: 1;
}

.weather-temp {
  color: var(--text-primary, #e4e4e7);
  font-weight: 500;
}
</style>
