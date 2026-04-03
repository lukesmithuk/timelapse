<template>
  <nav class="navbar">
    <router-link to="/" class="navbar-brand">Timelapse</router-link>
    <button class="navbar-toggle" @click="open = !open" aria-label="Toggle navigation">
      <span class="navbar-toggle__icon" :class="{ 'navbar-toggle__icon--open': open }">
        <span></span><span></span><span></span>
      </span>
    </button>
    <div class="navbar-links" :class="{ 'navbar-links--open': open }">
      <router-link to="/" active-class="active" exact @click="open = false">Dashboard</router-link>
      <router-link to="/gallery" active-class="active" @click="open = false">Gallery</router-link>
      <router-link to="/videos" active-class="active" @click="open = false">Videos</router-link>
      <router-link v-if="canRender" to="/render" active-class="active" @click="open = false">Render</router-link>
    </div>
  </nav>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  canRender: { type: Boolean, default: true },
})

const open = ref(false)
</script>

<style scoped>
.navbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  background: var(--bg-secondary, #141720);
  border-bottom: 1px solid var(--border, #2a2d3a);
  padding: 0 1rem;
  height: auto;
  min-height: 3rem;
}

.navbar-brand {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--accent-green, #4ade80);
  text-decoration: none;
  letter-spacing: 0.03em;
  padding: 0.75rem 0;
}

.navbar-toggle {
  display: none;
  background: none;
  border: none;
  padding: 0.4rem;
  margin-left: auto;
  cursor: pointer;
}

.navbar-toggle__icon {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 20px;
}

.navbar-toggle__icon span {
  display: block;
  height: 2px;
  width: 100%;
  background: var(--text-secondary, #8b8d98);
  border-radius: 1px;
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.navbar-toggle__icon--open span:nth-child(1) {
  transform: translateY(6px) rotate(45deg);
}

.navbar-toggle__icon--open span:nth-child(2) {
  opacity: 0;
}

.navbar-toggle__icon--open span:nth-child(3) {
  transform: translateY(-6px) rotate(-45deg);
}

.navbar-links {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin-left: 1.5rem;
}

.navbar-links a {
  color: var(--text-secondary, #8b8d98);
  text-decoration: none;
  font-size: 0.85rem;
  font-weight: 500;
  padding: 0.5rem 0.7rem;
  border-radius: var(--radius-sm, 4px);
  transition: color 0.15s ease, background 0.15s ease;
}

.navbar-links a:hover {
  color: var(--text-primary, #e4e4e7);
  background: rgba(255, 255, 255, 0.04);
}

.navbar-links a.active {
  color: var(--accent-green, #4ade80);
  background: rgba(74, 222, 128, 0.08);
}

/* Mobile: hamburger menu */
@media (max-width: 639px) {
  .navbar-toggle {
    display: block;
  }

  .navbar-links {
    display: none;
    flex-direction: column;
    align-items: stretch;
    width: 100%;
    margin-left: 0;
    gap: 0;
    padding: 0.25rem 0 0.5rem;
    border-top: 1px solid var(--border, #2a2d3a);
  }

  .navbar-links--open {
    display: flex;
  }

  .navbar-links a {
    padding: 0.6rem 0.5rem;
    font-size: 0.9rem;
    border-radius: var(--radius-sm, 4px);
  }
}
</style>
