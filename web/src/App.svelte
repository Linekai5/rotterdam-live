<script>
  import MapComponent from './lib/MapComponent.svelte';
</script>

<main>
  <MapComponent />
</main>

<style>
  @font-face { font-family: 'Instrument Sans'; src: url('/fonts/InstrumentSans.ttf') format('truetype'); font-weight: 400 700; font-display: swap; }
  :global(html, body, #app) {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background-color: #082632;
    font-family: 'Instrument Sans', 'Helvetica Neue', Arial, sans-serif;
  }

  main {
    position: relative;
    width: 100%;
    height: 100%;
  }
</style>
