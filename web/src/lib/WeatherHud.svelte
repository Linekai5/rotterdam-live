<script>
  import { WEATHER_SIMULATOR_PRESETS } from './weatherEngine.js';

  export let weatherController = null;
  export let weatherState = {
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

  let inspectorOpen = false;
  const presetList = Object.values(WEATHER_SIMULATOR_PRESETS);

  function selectPreset(id) {
    if (weatherController) {
      weatherController.setPreset(id);
    }
  }

  function toggleWeatherLayer() {
    if (weatherController) {
      weatherController.setEnabled(!weatherState.enabled);
    }
  }

  function compassLabel(deg) {
    const dirs = ['N', 'NNO', 'NO', 'ONO', 'O', 'OZO', 'ZO', 'ZZO', 'Z', 'ZZW', 'ZW', 'WZW', 'W', 'WNW', 'NW', 'NNW'];
    const idx = Math.round(((deg ?? 0) % 360) / 22.5) % 16;
    return dirs[idx];
  }
</script>

<div class="weather-hud-root" aria-label="Rotterdam Tactical Weather HUD">
  <!-- Minimalist Obsidian Telemetry Pill -->
  <div class="hud-pill">
    <button
      type="button"
      class="hud-status-badge {weatherState.isLive ? 'is-live' : 'is-sim'}"
      on:click={() => (inspectorOpen = !inspectorOpen)}
      title="Toggle Live KNMI / Weather Simulator Inspector"
    >
      <span class="status-dot"></span>
      <span class="status-text">{weatherState.isLive ? 'KNMI LIVE' : 'SIM OVERRIDE'}</span>
    </button>

    <div class="hud-divider"></div>

    <!-- Temperature -->
    <div class="hud-metric" title="Rotterdam 12-Node Mean Air Temperature">
      <span class="metric-value">{weatherState.temperatureC.toFixed(1)}°C</span>
    </div>

    <div class="hud-divider"></div>

    <!-- Wind Speed & Compass Arrow -->
    <div class="hud-metric wind-metric" title="10m Wind Vector ({weatherState.windDirectionDeg}°)">
      <svg
        class="compass-arrow"
        width="13"
        height="13"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.4"
        style="transform: rotate({(weatherState.windDirectionDeg + 180) % 360}deg);"
      >
        <path d="M12 19V5M5 12l7-7 7 7" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      <span class="metric-value">{weatherState.windSpeedKmh.toFixed(0)}</span>
      <span class="metric-unit">km/h {compassLabel(weatherState.windDirectionDeg)}</span>
    </div>

    <div class="hud-divider"></div>

    <!-- Precipitation Rate -->
    <div class="hud-metric" title="Precipitation Rate (mm/h)">
      <span class="metric-label">RAIN</span>
      <span class="metric-value {weatherState.precipitationMmH > 0.1 ? 'active-rain' : ''}">
        {weatherState.precipitationMmH.toFixed(1)}
      </span>
      <span class="metric-unit">mm/h</span>
    </div>

    <div class="hud-divider"></div>

    <!-- Cloud Cover % -->
    <div class="hud-metric" title="Volumetric Cloud Cover (%)">
      <span class="metric-label">CLOUDS</span>
      <span class="metric-value">{weatherState.cloudCoverPct}%</span>
    </div>

    <!-- Expand / Collapse Inspector Toggle -->
    <button
      type="button"
      class="inspector-toggle-btn {inspectorOpen ? 'open' : ''}"
      on:click={() => (inspectorOpen = !inspectorOpen)}
      aria-expanded={inspectorOpen}
      aria-label="Open Weather Simulator Inspector"
      title="Expand Weather Simulator & 12-Node Grid Inspector"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>
  </div>

  <!-- Expandable Live / Simulator Override Inspector Drawer -->
  {#if inspectorOpen}
    <div class="inspector-drawer">
      <div class="drawer-header">
        <div>
          <div class="drawer-title">VOLUMETRIC WEATHER ENGINE</div>
          <div class="drawer-subtitle">
            {weatherState.weatherDescription} · {weatherState.altitudePhase}
          </div>
        </div>
        <button
          type="button"
          class="layer-power-btn {weatherState.enabled ? 'on' : 'off'}"
          on:click={toggleWeatherLayer}
        >
          {weatherState.enabled ? 'SHADER ON' : 'SHADER OFF'}
        </button>
      </div>

      <div class="section-heading">TELEMETRY SOURCE / SIMULATOR PRESETS</div>
      <div class="presets-list">
        {#each presetList as preset (preset.id)}
          <button
            type="button"
            class="preset-btn {weatherState.presetId === preset.id ? 'active' : ''}"
            on:click={() => selectPreset(preset.id)}
          >
            <div class="preset-top">
              <span class="preset-name">{preset.label}</span>
              {#if preset.isLive}
                <span class="preset-tag live-tag">HARMONIE 2KM</span>
              {/if}
            </div>
            <div class="preset-desc">{preset.subtitle}</div>
          </button>
        {/each}
      </div>

      {#if weatherState.nodes && weatherState.nodes.length >= 12}
        <div class="section-heading">COASTAL-TO-INLAND MICRO-GRID SAMPLE</div>
        <div class="microgrid-strip">
          <div class="grid-cell">
            <span class="cell-zone">WEST COAST</span>
            <span class="cell-name">Maasvlakte</span>
            <span class="cell-stats">
              {weatherState.nodes[0].temperature_2m}°C · {weatherState.nodes[0].wind_speed_10m} km/h · {weatherState.nodes[0].precipitation} mm/h
            </span>
          </div>
          <div class="grid-cell">
            <span class="cell-zone">URBAN CORE</span>
            <span class="cell-name">Centrum</span>
            <span class="cell-stats">
              {weatherState.nodes[6].temperature_2m}°C · {weatherState.nodes[6].wind_speed_10m} km/h · {weatherState.nodes[6].precipitation} mm/h
            </span>
          </div>
          <div class="grid-cell">
            <span class="cell-zone">EAST INLAND</span>
            <span class="cell-name">Nesselande</span>
            <span class="cell-stats">
              {weatherState.nodes[11].temperature_2m}°C · {weatherState.nodes[11].wind_speed_10m} km/h · {weatherState.nodes[11].precipitation} mm/h
            </span>
          </div>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .weather-hud-root {
    position: fixed;
    top: 18px;
    right: 18px;
    z-index: 120;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 8px;
    pointer-events: auto;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    user-select: none;
  }

  .hud-pill {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 12px;
    background: rgba(11, 15, 23, 0.88);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 999px;
    color: #f1f5f9;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.06);
    font-size: 11.5px;
    letter-spacing: 0.02em;
  }

  .hud-status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(30, 41, 59, 0.75);
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 999px;
    padding: 3px 9px;
    color: #e2e8f0;
    font-family: inherit;
    font-size: 10px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.16s ease;
  }

  .hud-status-badge:hover {
    border-color: rgba(148, 163, 184, 0.45);
    background: rgba(51, 65, 85, 0.85);
  }

  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 8px #10b981;
  }

  .hud-status-badge.is-sim .status-dot {
    background: #f59e0b;
    box-shadow: 0 0 8px #f59e0b;
  }

  .hud-divider {
    width: 1px;
    height: 14px;
    background: rgba(148, 163, 184, 0.18);
  }

  .hud-metric {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
  }

  .metric-label {
    font-size: 9.5px;
    color: #64748b;
    font-weight: 600;
  }

  .metric-value {
    font-weight: 700;
    color: #f8fafc;
  }

  .metric-value.active-rain {
    color: #38bdf8;
  }

  .metric-unit {
    font-size: 10px;
    color: #94a3b8;
  }

  .compass-arrow {
    color: #38bdf8;
    transition: transform 0.35s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .inspector-toggle-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    border: 1px solid rgba(148, 163, 184, 0.18);
    background: rgba(30, 41, 59, 0.65);
    color: #cbd5e1;
    cursor: pointer;
    padding: 0;
    transition: all 0.18s ease;
  }

  .inspector-toggle-btn:hover {
    background: rgba(51, 65, 85, 0.9);
    color: #ffffff;
  }

  .inspector-toggle-btn.open svg {
    transform: rotate(180deg);
  }

  .inspector-drawer {
    width: 320px;
    background: rgba(9, 13, 22, 0.94);
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 14px;
    padding: 14px;
    color: #e2e8f0;
    box-shadow: 0 18px 42px rgba(0, 0, 0, 0.68);
  }

  .drawer-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 8px;
    padding-bottom: 10px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.14);
    margin-bottom: 10px;
  }

  .drawer-title {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: #f8fafc;
  }

  .drawer-subtitle {
    font-size: 10px;
    color: #94a3b8;
    margin-top: 2px;
  }

  .layer-power-btn {
    font-family: inherit;
    font-size: 9.5px;
    font-weight: 700;
    padding: 4px 8px;
    border-radius: 6px;
    cursor: pointer;
    border: 1px solid rgba(16, 185, 129, 0.4);
    background: rgba(16, 185, 129, 0.14);
    color: #34d399;
  }

  .layer-power-btn.off {
    border-color: rgba(148, 163, 184, 0.25);
    background: rgba(30, 41, 59, 0.5);
    color: #94a3b8;
  }

  .section-heading {
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #64748b;
    margin-bottom: 6px;
  }

  .presets-list {
    display: flex;
    flex-direction: column;
    gap: 5px;
    margin-bottom: 12px;
  }

  .preset-btn {
    text-align: left;
    font-family: inherit;
    background: rgba(15, 23, 42, 0.72);
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 8px;
    padding: 7px 10px;
    color: #e2e8f0;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .preset-btn:hover {
    background: rgba(30, 41, 59, 0.85);
    border-color: rgba(148, 163, 184, 0.32);
  }

  .preset-btn.active {
    background: rgba(30, 58, 138, 0.42);
    border-color: #38bdf8;
    box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.25);
  }

  .preset-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .preset-name {
    font-size: 11px;
    font-weight: 700;
    color: #f8fafc;
  }

  .preset-tag {
    font-size: 8.5px;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 4px;
    background: rgba(16, 185, 129, 0.18);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.35);
  }

  .preset-desc {
    font-size: 9.5px;
    color: #94a3b8;
    margin-top: 2px;
  }

  .microgrid-strip {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
  }

  .grid-cell {
    background: rgba(15, 23, 42, 0.75);
    border: 1px solid rgba(148, 163, 184, 0.12);
    border-radius: 7px;
    padding: 6px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .cell-zone {
    font-size: 8px;
    color: #64748b;
    font-weight: 700;
  }

  .cell-name {
    font-size: 10px;
    color: #f1f5f9;
    font-weight: 700;
  }

  .cell-stats {
    font-size: 8.5px;
    color: #94a3b8;
    line-height: 1.3;
  }

  @media (max-width: 640px) {
    .weather-hud-root {
      top: 10px;
      right: 10px;
      left: 10px;
    }

    .hud-pill {
      width: 100%;
      justify-content: space-between;
      overflow-x: auto;
    }

    .inspector-drawer {
      width: 100%;
      box-sizing: border-box;
    }
  }
</style>

