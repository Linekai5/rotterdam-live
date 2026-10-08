<script>
  import { switchStyle, toggleLabels, toggle3DBuildings, resetView } from './map.js';

  export let map = null;

  let isOpen = false;
  const urlParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
  let activeMode = urlParams?.get('mode') || 'satellite';
  let showLabels = true;
  let show3DBuildings = false;

  function selectMode(mode) {
    activeMode = mode;
    if (map) {
      switchStyle(map, mode, { labels: showLabels, buildings3d: show3DBuildings });
    }
  }

  function handleLabelsChange() {
    showLabels = !showLabels;
    if (map) {
      toggleLabels(map, showLabels);
    }
  }

  function handle3DChange() {
    show3DBuildings = !show3DBuildings;
    if (map) {
      toggle3DBuildings(map, show3DBuildings);
    }
  }

  function handleReset() {
    if (map) {
      resetView(map);
    }
  }
</script>

<div class="layer-control-wrapper">
  <!-- Trigger Button -->
  <button 
    class="trigger-btn" 
    on:click={() => (isOpen = !isOpen)}
    aria-label="Toggle map layers"
    title="Map layers & filters"
  >
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
      <polyline points="2 17 12 22 22 17"></polyline>
      <polyline points="2 12 12 17 22 12"></polyline>
    </svg>
    <span class="btn-label">Layers</span>
  </button>

  <!-- Expandable Panel -->
  {#if isOpen}
    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">Map Type</span>
        <button class="close-btn" on:click={() => (isOpen = false)}>✕</button>
      </div>

      <!-- Mode Cards Grid -->
      <div class="modes-grid">
        <!-- Clean -->
        <button 
          class="mode-card {activeMode === 'clean' ? 'active' : ''}" 
          on:click={() => selectMode('clean')}
        >
          <div class="thumbnail thumb-clean">
            <div class="mini-island-clean"></div>
          </div>
          <span class="mode-name">Clean</span>
        </button>

        <!-- Satellite -->
        <button 
          class="mode-card {activeMode === 'satellite' ? 'active' : ''}" 
          on:click={() => selectMode('satellite')}
        >
          <div class="thumbnail thumb-satellite">
            <div class="mini-island-sat"></div>
          </div>
          <span class="mode-name">Satellite</span>
        </button>

        <!-- Dark -->
        <button 
          class="mode-card {activeMode === 'dark' ? 'active' : ''}" 
          on:click={() => selectMode('dark')}
        >
          <div class="thumbnail thumb-dark">
            <div class="mini-island-dark"></div>
          </div>
          <span class="mode-name">Dark</span>
        </button>
      </div>

      <div class="divider"></div>

      <!-- Detail Toggles -->
      <div class="panel-section-title">Map Details</div>
      
      <label class="toggle-row">
        <input 
          type="checkbox" 
          checked={showLabels} 
          on:change={handleLabelsChange} 
        />
        <span class="toggle-text">Labels</span>
      </label>

      <label class="toggle-row">
        <input 
          type="checkbox" 
          checked={show3DBuildings} 
          on:change={handle3DChange} 
        />
        <span class="toggle-text">3D Buildings</span>
      </label>

      <div class="divider"></div>

      <!-- Recenter Button -->
      <button class="recenter-btn" on:click={handleReset}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <circle cx="12" cy="12" r="3"></circle>
        </svg>
        <span>Recenter Rotterdam</span>
      </button>
    </div>
  {/if}
</div>

<style>
  .layer-control-wrapper {
    position: fixed;
    bottom: 24px;
    left: 24px;
    z-index: 100;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  }

  .trigger-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    background: rgba(255, 255, 255, 0.95);
    color: #1f2937;
    border: 1px solid rgba(0, 0, 0, 0.08);
    padding: 10px 14px;
    border-radius: 12px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12), 0 1px 3px rgba(0, 0, 0, 0.08);
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
    backdrop-filter: blur(8px);
    transition: all 0.2s ease;
  }

  .trigger-btn:hover {
    background: #ffffff;
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.16);
  }

  .panel {
    position: absolute;
    bottom: 50px;
    left: 0;
    width: 270px;
    background: rgba(255, 255, 255, 0.96);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 16px;
    padding: 16px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.16), 0 2px 6px rgba(0, 0, 0, 0.06);
    animation: fadeIn 0.18s ease-out;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }

  .panel-title {
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #4b5563;
  }

  .close-btn {
    background: transparent;
    border: none;
    color: #9ca3af;
    cursor: pointer;
    font-size: 14px;
    padding: 2px 6px;
    border-radius: 6px;
  }

  .close-btn:hover {
    background: #f3f4f6;
    color: #111827;
  }

  .modes-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-bottom: 12px;
  }

  .mode-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    background: transparent;
    border: 2px solid transparent;
    border-radius: 10px;
    padding: 4px;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .mode-card:hover {
    background: #f3f4f6;
  }

  .mode-card.active {
    border-color: #2563eb;
    background: #eff6ff;
  }

  .thumbnail {
    width: 60px;
    height: 48px;
    border-radius: 8px;
    margin-bottom: 6px;
    overflow: hidden;
    position: relative;
    border: 1px solid rgba(0, 0, 0, 0.1);
  }

  .thumb-clean {
    background: #c2c8ca;
  }

  .mini-island-clean {
    width: 32px;
    height: 24px;
    background: #f8fafc;
    border-radius: 50% 40% 60% 30%;
    margin: 12px auto;
  }

  .thumb-satellite {
    background: #082632;
  }

  .mini-island-sat {
    width: 34px;
    height: 26px;
    background: #2e5939;
    border-radius: 40% 60% 45% 55%;
    margin: 11px auto;
  }

  .thumb-dark {
    background: #0c0c0c;
  }

  .mini-island-dark {
    width: 32px;
    height: 24px;
    background: #1e293b;
    border-radius: 50% 40% 60% 30%;
    margin: 12px auto;
  }

  .mode-name {
    font-size: 11px;
    font-weight: 600;
    color: #374151;
  }

  .divider {
    height: 1px;
    background: #e5e7eb;
    margin: 10px 0;
  }

  .panel-section-title {
    font-size: 12px;
    font-weight: 600;
    color: #6b7280;
    margin-bottom: 8px;
  }

  .toggle-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    font-size: 13px;
    color: #1f2937;
    cursor: pointer;
  }

  .toggle-row input {
    cursor: pointer;
    accent-color: #2563eb;
  }

  .recenter-btn {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    color: #374151;
    font-size: 12px;
    font-weight: 600;
    padding: 8px;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.2s;
  }

  .recenter-btn:hover {
    background: #f3f4f6;
    color: #111827;
  }
</style>
