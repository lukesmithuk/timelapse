<template>
  <NavBar :canRender="canRender" />
  <main class="content">
    <router-view :access="access" />
  </main>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from './api'
import NavBar from './components/NavBar.vue'

const access = ref('viewer')

const canRender = computed(() => access.value === 'local' || access.value === 'admin')

async function fetchAccess() {
  try {
    const status = await api.getStatus()
    access.value = status.access ?? 'viewer'
  } catch {
    // Default to local if status fails
  }
}

onMounted(fetchAccess)
</script>
