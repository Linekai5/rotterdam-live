<script>
  import MapComponent from './lib/MapComponent.svelte';
</script>

<main>
  <MapComponent />
</main>

<style>
  :global(html, body, #app) {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background-color: #082632;
  }

  main {
    position: relative;
    width: 100%;
    height: 100%;
  }
</style>
