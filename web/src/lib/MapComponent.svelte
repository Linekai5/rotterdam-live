<script>
  import { onMount, onDestroy } from 'svelte';
  import { initMap } from './map.js';
  import { API_BASE_URL } from './liveLayers.js';
  import { createWeatherEngineController } from './weatherEngine.js';
  import WeatherHud from './WeatherHud.svelte';

  let mapElement;
  let map = null;
  let pingInterval = null;
  let weatherController = null;
  let weatherState = { status: 'unavailable', enabled: true, nodes: [] };

  // Active background connection with the API
  async function checkApiConnection() {
    try {
      await fetch(`${API_BASE_URL}/health/live`, {
        cache: 'no-store',
        headers: { 'Accept': 'application/json' }
      });
    } catch (err) {
      // silent background connection check
    }
  }

  onMount(async () => {
    // 1. Maintain active background connection with API
    checkApiConnection();
    pingInterval = setInterval(checkApiConnection, 10000);

    // 2. Initialize the map and validated live weather controller.
    try {
      map = await initMap(mapElement, (loadedMap) => {
        map = loadedMap;
        if (typeof window !== 'undefined') window.map = loadedMap;
      });
      if (typeof window !== 'undefined') window.map = map;

      weatherController = createWeatherEngineController(map, (nextState) => {
        weatherState = nextState;
      });
      if (typeof window !== 'undefined') window.weatherController = weatherController;
    } catch (err) {
      console.error('MapComponent: initMap error!', err);
    }
  });

  onDestroy(() => {
    if (pingInterval) clearInterval(pingInterval);
    if (map) {
      map.remove();
    }
  });

  const urlParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
  const initialMode = urlParams?.get('mode') || 'satellite';
  const defaultBg = initialMode === 'satellite' ? '#082632' : (initialMode === 'dark' ? '#0c0c0c' : '#c2c8ca');
</script>

<div class="map-wrapper">
  <!-- Interactive map: pan, zoom, pitch (0-65°) and bearing rotation. -->
  <div bind:this={mapElement} class="map-container" style="background-color: {defaultBg}"></div>

  <!-- Live weather card with source time, status and radar attribution. -->
  <WeatherHud {weatherController} {weatherState} />
</div>

<style>
  .map-wrapper {
    position: fixed;
    inset: 0;
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    pointer-events: auto;
  }

  .map-container {
    width: 100%;
    height: 100%;
    position: absolute;
    inset: 0;
    background-color: #0c0c0c;
    pointer-events: auto;
    touch-action: none;
  }

  .map-container :global(:focus) {
    outline: none !important;
    box-shadow: none !important;
  }
</style>

