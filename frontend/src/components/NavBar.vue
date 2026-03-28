<template>
  <nav class="navbar">
    <router-link to="/" class="navbar-brand">Timelapse</router-link>
    <div class="navbar-links">
      <router-link to="/" active-class="active" exact>Dashboard</router-link>
      <router-link to="/gallery" active-class="active">Gallery</router-link>
      <router-link to="/videos" active-class="active">Videos</router-link>
      <router-link to="/render" active-class="active">Render</router-link>
    </div>
  </nav>
</template>
