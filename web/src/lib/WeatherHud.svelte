<script>
  export let weatherController = null;
  export let weatherState = { status: 'unavailable', nodes: [] };
  let detailsOpen = false;
  const format = (value, digits = 0) => Number.isFinite(value) ? value.toFixed(digits) : '—';
  const timeLabel = value => value ? new Date(value).toLocaleTimeString('nl-NL', { timeZone: 'Europe/Amsterdam', hour: '2-digit', minute: '2-digit' }) : '—';
  function compass(deg) {
    return Number.isFinite(deg) ? ['N', 'NNO', 'NO', 'ONO', 'O', 'OZO', 'ZO', 'ZZO', 'Z', 'ZZW', 'ZW', 'WZW', 'W', 'WNW', 'NW', 'NNW'][Math.round(deg / 22.5) % 16] : '—';
  }
</script>

<aside class="weather-hud" class:details-open={detailsOpen} aria-label="Rotterdam weather">
  <button class="weather-summary" on:click={() => detailsOpen = !detailsOpen} aria-expanded={detailsOpen} aria-label="Rotterdam weather details">
    <div class="heading"><span>ROTTERDAM</span><span class="status"><i></i>{weatherState.status === 'live' ? 'Live' : weatherState.status === 'stale' ? 'Outdated' : 'Unavailable'}<span class:expanded={detailsOpen} class="chevron">⌄</span></span></div>
    {#if weatherState.nodes?.length}
      <div class="conditions"><span class="temperature">{format(weatherState.temperatureC, 1)}<small>°</small></span><div class="condition-copy"><span>{weatherState.weatherDescription}</span><span class="wind">{format(weatherState.windSpeedKmh)} km/h · {compass(weatherState.windDirectionDeg)}</span></div></div>
      <div class="metrics"><span>Cloud cover <b>{format(weatherState.cloudCoverPct)}%</b></span><span>Rain <b>{format(weatherState.precipitationMmH, 1)} <small>mm/h</small></b></span></div>
    {:else}<p class="empty">Waiting for current weather</p>{/if}
  </button>
  <div class="source-line"><span>Centrum · {timeLabel(weatherState.validAt)}</span>{#if weatherState.radarAt}<a href="https://www.rainviewer.com/" target="_blank" rel="noreferrer">Radar {timeLabel(weatherState.radarAt)} · RainViewer</a>{:else}<span>{weatherState.radarEnabled ? 'Radar unavailable' : 'Radar off'}</span>{/if}</div>
  {#if detailsOpen}
    <div class="weather-details">
      <div class="detail-row"><span>Source</span><span>KNMI via Open-Meteo</span></div>
      <div class="detail-row"><span>Valid at</span><span>{timeLabel(weatherState.validAt)} · Rotterdam time</span></div>
      <p>Model conditions for Rotterdam Centrum. Clouds illustrate low, middle and high cloud cover; they fade as you zoom into the streets.</p>
      <p>Rain intensity is a model estimate. The radar overlay shows observed precipitation.</p>
      {#if weatherState.status === 'stale'}<p>These values are outdated. Weather effects resume when fresh data returns.</p>{/if}
      <button class="refresh" on:click={() => weatherController?.refreshLive()}>Refresh weather <span aria-hidden="true">↻</span></button>
    </div>
  {/if}
</aside>

<style>
  .weather-hud { position: fixed; top: 20px; right: 20px; z-index: 120; width: 286px; max-width: calc(100vw - 32px); color: #e6e4df; background: #202322f5; border: 1px solid #ffffff1c; border-radius: 13px; box-shadow: 0 8px 28px #0003; font: 12px system-ui, sans-serif; overflow: hidden; max-height: calc(100dvh - 40px); overflow-y: auto; scrollbar-width: thin; }
  button { font: inherit; color: inherit; cursor: pointer; }
  .weather-summary { display: block; width: 100%; padding: 16px 17px 13px; background: transparent; border: 0; text-align: left; }
  .weather-summary:hover { background: #ffffff04; }
  .heading { display: flex; align-items: center; justify-content: space-between; font-size: 10px; letter-spacing: .12em; color: #aab0a7; }
  .heading > span:first-child { color: #b5b9b3; font-weight: 600; }
  .status { display: flex; align-items: center; gap: 6px; color: #b7bcb5; letter-spacing: 0; font-size: 11px; }
  i { width: 5px; height: 5px; border-radius: 50%; background: #a3aca0; }
  .chevron { margin-left: 7px; font-size: 15px; transition: transform .2s; }
  .expanded { transform: rotate(180deg); }
  .conditions { display: flex; align-items: center; gap: 17px; padding: 13px 0 15px; }
  .temperature { font-size: 42px; font-weight: 400; letter-spacing: -.06em; line-height: 1.1; font-variant-numeric: tabular-nums; }
  .temperature small { font-size: 30px; vertical-align: top; }
  .condition-copy { display: grid; gap: 5px; font-size: 12px; color: #d1d3ce; }
  .wind { font-size: 11px; color: #a3a9a2; }
  .metrics { display: flex; justify-content: space-between; gap: 12px; border-top: 1px solid #ffffff12; padding-top: 12px; font-size: 10px; color: #a3a9a2; }
  .metrics b { margin-left: 5px; font-size: 12px; font-weight: 500; color: #dedfd9; }
  .metrics small { font-size: 10px; color: #a3a9a2; }
  .source-line { display: flex; justify-content: space-between; gap: 8px; padding: 9px 17px; background: #00000016; color: #8e968d; font-size: 9px; }
  a { color: inherit; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .weather-details { padding: 14px 17px; border-top: 1px solid #ffffff12; font-size: 11px; line-height: 1.6; }
  .detail-row { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 5px; color: #b4bab2; }
  .detail-row > span:first-child { color: #899286; }
  p { color: #a3aba0; margin: 12px 0; }
  .refresh { display: flex; justify-content: space-between; width: 100%; border: 1px solid #ffffff20; border-radius: 6px; background: #ffffff04; padding: 7px 10px; margin-top: 13px; }
  button:focus-visible, a:focus-visible { outline: 2px solid #bdc4b8; outline-offset: -3px; }
  .empty { margin-bottom: 0; }
  @media (max-width: 700px) {
    .weather-hud:not(.details-open) { width: 148px; top: 12px; right: 12px; }
    .weather-hud:not(.details-open) .weather-summary { padding: 10px 13px; }
    .weather-hud:not(.details-open) .heading > span:first-child,
    .weather-hud:not(.details-open) .condition-copy,
    .weather-hud:not(.details-open) .metrics,
    .weather-hud:not(.details-open) .source-line a { display: none; }
    .weather-hud:not(.details-open) .heading { justify-content: flex-end; }
    .weather-hud:not(.details-open) .conditions { padding: 5px 0 0; }
    .weather-hud:not(.details-open) .temperature { font-size: 29px; }
    .weather-hud:not(.details-open) .temperature small { font-size: 22px; }
    .weather-hud:not(.details-open) .source-line { padding: 7px 13px; }
    .weather-hud.details-open { width: calc(100vw - 24px); }
  }
  @media (max-width: 480px) { .weather-hud { top: 12px; right: 12px; width: 260px; } .temperature { font-size: 36px; } .weather-summary { padding: 13px 15px; } }
</style>
