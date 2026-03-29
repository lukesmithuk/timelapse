<template>
  <NavBar />
  <main class="content">
    <router-view />
  </main>
</template>

<script setup>
import NavBar from './components/NavBar.vue'
</script>
