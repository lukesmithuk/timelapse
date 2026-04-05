<script setup>
const props = defineProps({
  weather: { type: Object, required: true },
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
  <div class="weather-detail">
    <div class="weather-grid">
      <div class="weather-field">
        <span class="weather-label">Conditions</span>
        <span class="weather-value">{{ weatherIcon(weather.conditions) }} {{ weather.conditions || 'Unknown' }}</span>
      </div>
      <div class="weather-field">
        <span class="weather-label">Temperature</span>
        <span class="weather-value">{{ weather.temperature != null ? Math.round(weather.temperature) + '\u00B0C' : '-' }}</span>
      </div>
      <div class="weather-field">
        <span class="weather-label">Humidity</span>
        <span class="weather-value">{{ weather.humidity != null ? weather.humidity + '%' : '-' }}</span>
      </div>
      <div class="weather-field">
        <span class="weather-label">Wind speed</span>
        <span class="weather-value">{{ weather.wind_speed != null ? weather.wind_speed + ' km/h' : '-' }}</span>
      </div>
      <div class="weather-field">
        <span class="weather-label">Precipitation</span>
        <span class="weather-value">{{ weather.precipitation != null ? weather.precipitation + ' mm' : '-' }}</span>
      </div>
      <div class="weather-field">
        <span class="weather-label">Cloud cover</span>
        <span class="weather-value">{{ weather.cloud_cover != null ? weather.cloud_cover + '%' : '-' }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.weather-detail {
  background: var(--bg-card, #1a1d27);
  border: 1px solid var(--border, #2a2d3a);
  border-radius: 8px;
  padding: 12px;
}

.weather-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
}

.weather-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.weather-label {
  font-size: 11px;
  color: var(--text-secondary, #8b8d98);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.weather-value {
  font-size: 13px;
  color: var(--text-primary, #e4e4e7);
  font-weight: 500;
}
</style>
