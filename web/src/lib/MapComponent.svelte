<script>
  import { onMount, onDestroy } from 'svelte';
  import { initMap } from './map.js';
  import { API_BASE_URL } from './liveLayers.js';

  let mapElement;
  let map = null;

  // Active API Connection Management
  let apiStatus = 'connecting'; // 'connected' | 'connecting' | 'disconnected'
  let latencyMs = null;
  let pingInterval = null;

  async function checkApiConnection() {
    const startTime = performance.now();
    try {
      const res = await fetch(`${API_BASE_URL}/health/live`, {
        cache: 'no-store',
        headers: { 'Accept': 'application/json' }
      });
      if (res.ok) {
        latencyMs = Math.round(performance.now() - startTime);
        apiStatus = 'connected';
      } else {
        apiStatus = 'disconnected';
      }
    } catch (err) {
      console.warn('[API Connection] Health ping failed:', err);
      apiStatus = 'disconnected';
    }
  }

  onMount(async () => {
    // 1. Maintain active background connection with API
    checkApiConnection();
    pingInterval = setInterval(checkApiConnection, 10000);

    // 2. Initialize clean, non-interactive map
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

  <!-- Centered "rotterdam will be live soon" div -->
  <div class="center-overlay">
    <div class="live-soon-card">
      <div class="status-pill">
        <span class="status-dot {apiStatus}"></span>
        <span class="status-label">
          {#if apiStatus === 'connected'}
            API ACTIVE
          {:else if apiStatus === 'connecting'}
            CONNECTING TO ENGINE
          {:else}
            CONNECTING...
          {/if}
        </span>
        {#if apiStatus === 'connected' && latencyMs !== null}
          <span class="latency-tag">{latencyMs}ms</span>
        {/if}
      </div>

      <h1 class="headline">rotterdam will be live soon</h1>
      <p class="subtext">Real-time situational intelligence & digital twin platform</p>

      <div class="card-footer">
        <span class="footer-dot"></span>
        <span class="footer-note">Telemetry Ingestion Active</span>
      </div>
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
    pointer-events: none; /* Make entire page non-interactive */
  }

  .map-container {
    width: 100%;
    height: 100%;
    position: absolute;
    inset: 0;
    background-color: #082632;
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
    padding: 20px;
    z-index: 50;
    pointer-events: none;
  }

  .live-soon-card {
    background: rgba(8, 24, 34, 0.78);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    box-shadow: 
      0 24px 64px rgba(0, 0, 0, 0.65),
      0 0 40px rgba(16, 185, 129, 0.08),
      inset 0 1px 1px rgba(255, 255, 255, 0.1);
    border-radius: 24px;
    padding: 36px 44px;
    text-align: center;
    max-width: 480px;
    width: 100%;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
    pointer-events: none;
    animation: fadeIn 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateY(12px) scale(0.98);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    padding: 5px 14px;
    border-radius: 100px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
  }

  .status-dot.connected {
    background-color: #10b981;
    box-shadow: 0 0 10px #10b981;
    animation: pulseGlow 2s infinite;
  }

  .status-dot.connecting {
    background-color: #f59e0b;
    box-shadow: 0 0 8px #f59e0b;
    animation: pulseGlow 1.2s infinite;
  }

  .status-dot.disconnected {
    background-color: #ef4444;
    box-shadow: 0 0 8px #ef4444;
  }

  @keyframes pulseGlow {
    0% {
      transform: scale(0.95);
      box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
    }
    70% {
      transform: scale(1.05);
      box-shadow: 0 0 0 8px rgba(16, 185, 129, 0);
    }
    100% {
      transform: scale(0.95);
      box-shadow: 0 0 0 0 rgba(16, 185, 129, 0);
    }
  }

  .status-label {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #e2e8f0;
  }

  .latency-tag {
    font-size: 10px;
    font-weight: 600;
    color: #10b981;
    background: rgba(16, 185, 129, 0.15);
    padding: 2px 6px;
    border-radius: 6px;
    letter-spacing: 0.02em;
  }

  .headline {
    margin: 4px 0 0 0;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", "Segoe UI", Roboto, sans-serif;
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.025em;
    color: #ffffff;
    line-height: 1.25;
    text-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
  }

  .subtext {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    color: #94a3b8;
    max-width: 380px;
  }

  .card-footer {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 8px;
    padding-top: 14px;
    border-top: 1px solid rgba(255, 255, 255, 0.07);
    width: 100%;
    justify-content: center;
  }

  .footer-dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background-color: #38bdf8;
  }

  .footer-note {
    font-size: 11px;
    color: #64748b;
    font-weight: 500;
    letter-spacing: 0.03em;
  }

  @media (max-width: 480px) {
    .live-soon-card {
      padding: 28px 24px;
    }
    .headline {
      font-size: 22px;
    }
    .subtext {
      font-size: 13px;
    }
  }
</style>
