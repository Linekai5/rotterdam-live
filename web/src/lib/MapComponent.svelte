<script>
  import { onMount, onDestroy } from 'svelte';
  import { initMap } from './map.js';
  import { API_BASE_URL } from './liveLayers.js';

  let mapElement;
  let map = null;
  let pingInterval = null;

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

    // 2. Initialize non-interactive map
    try {
      map = await initMap(mapElement, (loadedMap) => {
        map = loadedMap;
        if (typeof window !== 'undefined') window.map = loadedMap;
      });
      if (typeof window !== 'undefined') window.map = map;
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
  <!-- Map Canvas: Full-screen background, non-interactive -->
  <div bind:this={mapElement} class="map-container" style="background-color: {defaultBg}"></div>

  <!-- Centered "rotterdam will be live soon" div (Basic Dark Style) -->
  <div class="center-overlay">
    <div class="message-box">
      rotterdam will be live soon
    </div>
  </div>
</div>

<style>
  .map-wrapper {
    position: fixed;
    inset: 0;
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    user-select: none;
    pointer-events: none;
  }

  .map-container {
    width: 100%;
    height: 100%;
    position: absolute;
    inset: 0;
    background-color: #0c0c0c;
    pointer-events: none;
  }

  .map-container :global(:focus) {
    outline: none !important;
    box-shadow: none !important;
  }

  .center-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    z-index: 50;
    pointer-events: none;
  }

  .message-box {
    background-color: rgba(14, 14, 14, 0.92);
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 20px 32px;
    color: #e5e5e5;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 18px;
    font-weight: 500;
    letter-spacing: -0.01em;
    text-align: center;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6);
  }

  @media (max-width: 480px) {
    .message-box {
      font-size: 16px;
      padding: 16px 24px;
    }
  }
</style>
