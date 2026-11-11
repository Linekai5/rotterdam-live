<script>
  import { onMount, onDestroy } from 'svelte';
  import { initMap } from './map.js';
  import { API_BASE_URL } from './liveLayers.js';
  import { createWeatherEngineController } from './weatherEngine.js';
  import { t } from './i18n.js';
  import CityExplorer from './CityExplorer.svelte';
  import WeatherHud from './WeatherHud.svelte';

  let mapElement;
  let map = null;
  let pingInterval = null;
  let weatherController = null;
  let apiStatus = 'connecting';
  let mapError = false;
  let removed = false;
  let weatherState = { status: 'unavailable', enabled: true, nodes: [] };

  $: if (map) map.getCanvas().setAttribute('aria-label', $t('Map canvas'));

  // Active background connection with the API
  async function checkApiConnection() {
    try {
      const response = await fetch(`${API_BASE_URL}/health/live`, {
        cache: 'no-store',
        signal: AbortSignal.timeout(8000),
        headers: { 'Accept': 'application/json' }
      });
      if (!removed) apiStatus = response.ok ? 'connected' : 'offline';
    } catch (err) {
      if (!removed) apiStatus = 'offline';
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
      if (removed) { map.remove(); return; }
      if (typeof window !== 'undefined') window.map = map;

      weatherController = createWeatherEngineController(map, (nextState) => {
        weatherState = nextState;
      });
      if (typeof window !== 'undefined') window.weatherController = weatherController;
    } catch (err) {
      if (!removed) mapError = true;
      console.error('MapComponent: initMap error!', err);
    }
  });

  onDestroy(() => {
    removed = true;
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
  {#if map}<CityExplorer {map} {weatherController} {weatherState} {apiStatus} />{/if}
  {#if mapError}
    <div class="map-error" role="alert">
      <h1>{$t('The map couldn’t start.')}</h1>
      <p>{$t('Try reloading the page to reconnect to Rotterdam.')}</p>
      <button on:click={() => window.location.reload()}>{$t('Reload map')}</button>
    </div>
  {/if}
</div>

<style>
  .map-wrapper {
    position: fixed;
    inset: 0;
    width: 100vw;
    height: 100vh;
    height: 100dvh;
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

  .map-container :global(canvas:focus-visible) { outline: 2px solid #b0c19a; outline-offset: -4px; }
  .map-error { position: absolute; inset: 0; display: grid; place-content: center; padding: 25px; background: #191f1a; color: #dce3d1; font: 14px system-ui, sans-serif; }
  .map-error h1 { font: 36px Georgia, serif; }
  .map-error button { padding: 12px; border: 1px solid #9dab8a; border-radius: 8px; background: #303b2a; color: inherit; cursor: pointer; }
</style>

