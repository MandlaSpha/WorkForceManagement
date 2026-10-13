<script setup lang="ts">
// The Gijima logo is white lettering on a transparent background, so it sits on a black badge in
// both themes. The file is Gijima's own brand asset, served from public/. It is bound from a
// constant so the bundler and test runner treat it as a plain URL, not a module to resolve.
const LOGO_URL = '/gijima-logo.png'
</script>

<template>
  <span class="inline-flex rounded-md bg-black px-3 py-1.5">
    <img :src="LOGO_URL" alt="Gijima" width="322" height="99" class="h-6 w-auto" />
  </span>
</template>
