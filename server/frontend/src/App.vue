<template>
  <nav>
    <RouterLink to="/tracks">Tracks</RouterLink>
    <RouterLink to="/tags">Tags</RouterLink>
  </nav>
  <main>
    <RouterView />
  </main>
</template>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: sans-serif; background: #111; color: #eee; }
nav { display: flex; gap: 1rem; padding: 1rem; background: #222; }
nav a { color: #aaa; text-decoration: none; }
nav a.router-link-active { color: #fff; }
main { padding: 1.5rem; }
</style>
