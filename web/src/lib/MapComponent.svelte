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
  let weatherState = {
    presetId: 'live',
    isLive: true,
    enabled: true,
    temperatureC: 16.4,
    cloudCoverPct: 45,
    precipitationMmH: 0.0,
    windSpeedKmh: 18.2,
    windGustsKmh: 26.5,
    windDirectionDeg: 235,
    weatherDescription: 'Wisselend bewolkt',
    altitudePhase: 'MACRO CANOPY',
    canopyOpacity: 0.90,
    nodes: []
  };

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

    // 2. Initialize interactive Rotterdam Island map & 60FPS WebGL Weather Engine
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
  <!-- Interactive Map Canvas: 60FPS pan, zoom, pitch (0-65°) & bearing rotation -->
  <div bind:this={mapElement} class="map-container" style="background-color: {defaultBg}"></div>

  <!-- Minimalist Obsidian Tactical Weather HUD Pill & Live/Sim Debug Inspector -->
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

