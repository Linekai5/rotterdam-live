<script>
  import { onMount } from 'svelte';
  import { slide } from 'svelte/transition';
  import { quintOut } from 'svelte/easing';
  export let weatherController = null;
  export let weatherState = { status: 'unavailable', nodes: [] };
  let detailsOpen = false;
  let reduceMotion = false;
  onMount(() => { const preference = window.matchMedia('(prefers-reduced-motion: reduce)'); reduceMotion = preference.matches; const changed = event => reduceMotion = event.matches; preference.addEventListener('change', changed); return () => preference.removeEventListener('change', changed); });
  const format = (value, digits = 0) => Number.isFinite(value) ? value.toFixed(digits) : '—';
  const timeLabel = value => value ? new Date(value).toLocaleTimeString('nl-NL', { timeZone: 'Europe/Amsterdam', hour: '2-digit', minute: '2-digit' }) : '—';
  function compass(deg) {
    return Number.isFinite(deg) ? ['N', 'NNO', 'NO', 'ONO', 'O', 'OZO', 'ZO', 'ZZO', 'Z', 'ZZW', 'ZW', 'WZW', 'W', 'WNW', 'NW', 'NNW'][Math.round(deg / 22.5) % 16] : '—';
  }
</script>

<aside class="weather-hud" class:details-open={detailsOpen} aria-label="Rotterdam weather">
  <button class="weather-summary" on:click={() => detailsOpen = !detailsOpen} aria-expanded={detailsOpen} aria-label="Rotterdam weather details">
    <div class="heading"><span>WEATHER <span class="weather-location">/ CENTRUM</span></span><span class="status"><i></i>{weatherState.status === 'live' ? 'Live' : weatherState.status === 'stale' ? 'Outdated' : 'Unavailable'}<span class:expanded={detailsOpen} class="chevron">⌄</span></span></div>
    {#if weatherState.nodes?.length}
      <div class="conditions"><span class="temperature">{format(weatherState.temperatureC, 1)}<small>°</small></span><div class="condition-copy"><span>{weatherState.weatherDescription}</span><span class="wind">{format(weatherState.windSpeedKmh)} km/h · {compass(weatherState.windDirectionDeg)}</span></div></div>
      <div class="metrics"><span>Cloud cover <b>{format(weatherState.cloudCoverPct)}%</b></span><span>Rain <b>{format(weatherState.precipitationMmH, 1)} <small>mm/h</small></b></span></div>
    {:else}<p class="empty">Waiting for current weather</p>{/if}
  </button>
  <div class="source-line"><span>Centrum · {timeLabel(weatherState.validAt)}</span>{#if weatherState.radarAt}<a href="https://www.rainviewer.com/" target="_blank" rel="noreferrer">Radar {timeLabel(weatherState.radarAt)} · RainViewer</a>{:else}<span>{weatherState.radarEnabled ? 'Radar unavailable' : 'Radar off'}</span>{/if}</div>
  {#if detailsOpen}
    <div class="weather-details" transition:slide={{duration:reduceMotion ? 0 : 350,easing:quintOut}}>
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
  .weather-hud { position:fixed;top:24px;right:24px;z-index:120;width:270px;max-width:calc(100vw - 32px);max-height:calc(100dvh - 48px);overflow:auto;scrollbar-width:thin;background:#171a19fa;color:#efeee7;border:1px solid #ffffff20;border-radius:4px;box-shadow:0 8px 32px #0002;font:12px 'Instrument Sans','Helvetica Neue',Arial,sans-serif;animation:weather-in .8s .15s cubic-bezier(.16,1,.3,1) both}
  button{font:inherit;color:inherit;cursor:pointer}.weather-summary{display:block;width:100%;padding:17px 18px 15px;border:0;background:none;text-align:left;transition:background .2s}.weather-summary:hover{background:#ffffff03}.heading{display:flex;justify-content:space-between;gap:12px;align-items:center;font-size:9px;letter-spacing:1.1px;color:#c3c8bb}.weather-location{color:#8b9780}.status{display:flex;align-items:center;gap:5px;letter-spacing:0;font-size:10px;color:#adb99f}.status i{width:4px;height:4px;border-radius:50%;background:#a8b899}.chevron{font-size:15px;margin-left:4px;transition:transform .35s}.expanded{transform:rotate(180deg)}
  .conditions{display:flex;align-items:center;gap:16px;padding:15px 0 16px}.temperature{font-size:43px;font-weight:400;letter-spacing:-2.7px;line-height:1;font-variant-numeric:tabular-nums}.temperature small{font-size:31px;vertical-align:top}.condition-copy{display:grid;gap:7px;font-size:12px;line-height:1.3}.wind{font-size:11px;color:#9eac90}.metrics{display:flex;justify-content:space-between;gap:14px;padding-top:12px;border-top:1px solid #ffffff17;font-size:10px;color:#a3af95}.metrics b{color:#e0e7d6;font-size:12px;font-weight:500;margin-left:4px}.metrics small{font-size:10px;color:#a3af95}
  .source-line{display:flex;justify-content:space-between;gap:8px;padding:9px 18px;background:#b0c09806;border-top:1px solid #ffffff09;font-size:9px;color:#9eac90}.source-line a{color:inherit;text-decoration:none}.source-line a:hover{text-decoration:underline}.weather-details{padding:17px 18px;border-top:1px solid #ffffff16;font-size:12px;line-height:1.7}.detail-row{display:flex;justify-content:space-between;gap:12px;margin-bottom:9px;font-size:11px;color:#c4cfb8}.detail-row>span:first-child{color:#a1ae94}.weather-details p{margin:14px 0;color:#a6b398}.refresh{display:flex;align-items:center;justify-content:space-between;gap:14px;width:100%;padding:12px;border:1px solid #b3c39e44;background:#bdcca60b;border-radius:2px;color:#d1dec2;text-align:left;transition:background .2s}.refresh:hover{background:#bdcca61a}.refresh span{font-size:18px}button:focus-visible,a:focus-visible{outline:2px solid #c8d4b9;outline-offset:-3px}.empty{font-size:12px;color:#b0bca4;margin:18px 0 4px}
  @keyframes weather-in{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
  @media(max-width:700px){.weather-hud{top:17px;right:16px;max-height:calc(100dvh - 34px)}.weather-hud:not(.details-open){width:120px}.weather-hud:not(.details-open) .weather-summary{padding:11px 13px 9px}.weather-hud:not(.details-open) .heading>span:first-child,.weather-hud:not(.details-open) .condition-copy,.weather-hud:not(.details-open) .metrics,.weather-hud:not(.details-open) .source-line a{display:none}.weather-hud:not(.details-open) .heading{justify-content:space-between}.weather-hud:not(.details-open) .conditions{padding:7px 0 1px}.weather-hud:not(.details-open) .temperature{font-size:29px;letter-spacing:-1.7px}.weather-hud:not(.details-open) .temperature small{font-size:24px}.weather-hud:not(.details-open) .source-line{padding:7px 12px;font-size:8px}.weather-hud.details-open{width:calc(100vw - 32px)}.weather-hud:not(.details-open) .source-line>span:last-child{display:none}}
  @media(max-width:360px){.weather-hud:not(.details-open){width:98px}.weather-hud:not(.details-open) .source-line{padding:6px 10px}.weather-hud:not(.details-open) .source-line>span:first-child{font-size:8px}}
  @media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
