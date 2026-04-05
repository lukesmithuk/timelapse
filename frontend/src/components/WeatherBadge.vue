<script setup>
const props = defineProps({
  conditions: { type: String, default: '' },
  temperature: { type: Number, default: null },
  humidity: { type: Number, default: null },
  windSpeed: { type: Number, default: null },
  precipitation: { type: Number, default: null },
  cloudCover: { type: Number, default: null },
  tempHigh: { type: Number, default: null },
  tempLow: { type: Number, default: null },
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

import { computed } from 'vue'

const tooltip = computed(() => {
  const lines = []
  if (props.conditions) lines.push(props.conditions)
  if (props.temperature !== null) lines.push(`Temperature: ${Math.round(props.temperature)}°C`)
  if (props.tempHigh !== null && props.tempLow !== null) lines.push(`High/Low: ${Math.round(props.tempHigh)}°C / ${Math.round(props.tempLow)}°C`)
  if (props.humidity !== null) lines.push(`Humidity: ${props.humidity}%`)
  if (props.windSpeed !== null) lines.push(`Wind: ${props.windSpeed} km/h`)
  if (props.precipitation !== null) lines.push(`Precipitation: ${props.precipitation} mm`)
  if (props.cloudCover !== null) lines.push(`Cloud cover: ${props.cloudCover}%`)
  return lines.join('\n')
})
</script>

<template>
  <span class="weather-badge" v-if="temperature !== null || tempHigh !== null" :title="tooltip">
    <span class="weather-icon">{{ weatherIcon(conditions) }}</span>
    <span class="weather-temp">{{ Math.round(temperature ?? tempHigh) }}&deg;C</span>
    <span v-if="conditions" class="weather-conditions">{{ conditions }}</span>
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
  cursor: help;
}

.weather-icon {
  font-size: 14px;
  line-height: 1;
}

.weather-temp {
  color: var(--text-primary, #e4e4e7);
  font-weight: 500;
}

.weather-conditions {
  color: var(--text-secondary, #8b8d98);
}
</style>
