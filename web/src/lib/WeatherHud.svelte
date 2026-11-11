<script>
  import { onMount } from 'svelte';
  import { language, languageLocale, t, weatherCondition } from './i18n.js';
  export let weatherController = null;
  export let weatherState = { status: 'unavailable', nodes: [] };

  let expanded = typeof window === 'undefined' || !window.matchMedia('(max-width: 700px)').matches;
  let userToggled = false;
  let currentTime = new Date();
  const timeZone = 'Europe/Amsterdam';
  $: locale = languageLocale($language);
  $: dateFormat = new Intl.DateTimeFormat(locale, { weekday: 'short', day: '2-digit', month: 'short', timeZone });
  $: clockFormat = new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit', timeZone, timeZoneName: 'short' });
  $: compactClockFormat = new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit', timeZone });
  $: wholeNumber = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  $: decimalNumber = new Intl.NumberFormat(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  $: dateLabel = dateFormat.format(currentTime);
  $: clockLabel = clockFormat.format(currentTime);
  $: compactClockLabel = compactClockFormat.format(currentTime);

  onMount(() => {
    const breakpoint = window.matchMedia('(max-width: 700px)');
    const resize = event => { if (!userToggled) expanded = !event.matches; };
    const updateClock = () => currentTime = new Date();
    // Align the first update to the next minute instead of keeping a clock
    // that's up to half a minute behind after the minute changes.
    let timer;
    const tick = () => {
      updateClock();
      timer = setTimeout(tick, 60000 - (Date.now() % 60000));
    };
    const visibility = () => { if (document.visibilityState === 'visible') { clearTimeout(timer); tick(); } };
    breakpoint.addEventListener('change', resize);
    document.addEventListener('visibilitychange', visibility);
    tick();
    return () => { clearTimeout(timer); breakpoint.removeEventListener('change', resize); document.removeEventListener('visibilitychange', visibility); };
  });

  function toggle() { userToggled = true; expanded = !expanded; }
  const format = (value, formatter) => Number.isFinite(value) ? formatter.format(value) : '—';
  function timeLabel(value, formatter) {
    const date = new Date(value);
    return value && Number.isFinite(date.getTime()) ? formatter.format(date) : '—';
  }
  const directions = {
    en: ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'],
    nl: ['N', 'NNO', 'NO', 'ONO', 'O', 'OZO', 'ZO', 'ZZO', 'Z', 'ZZW', 'ZW', 'WZW', 'W', 'WNW', 'NW', 'NNW']
  };
  function compass(degrees, language) {
    if (!Number.isFinite(degrees)) return '—';
    const sector = (Math.round(degrees / 22.5) % 16 + 16) % 16;
    return directions[language][sector];
  }
</script>

<aside class="weather-hud" class:expanded aria-label={$t('Rotterdam weather')}>
  <button class="weather-summary" on:click={toggle} aria-expanded={expanded} aria-controls="weather-dashboard-content"
    aria-label={$t('Rotterdam weather details')} title={$t(expanded ? 'Collapse weather dashboard' : 'Expand weather dashboard')}>
    <div class="heading">
      <span class="heading-label">{$t('WEATHER')} <span class="weather-location">/ CENTRUM</span></span>
      <span class="status"><i></i>{$t(weatherState.status === 'live' ? 'Live' : weatherState.status === 'stale' ? 'Outdated' : 'Unavailable')}<span class:open={expanded} class="chevron">⌄</span></span>
    </div>
    <div class="conditions">
      <span class="temperature">{format(weatherState.temperatureC, decimalNumber)}<small>°</small></span>
      <div class="condition-copy" aria-hidden={!expanded}>
        <span>{weatherState.nodes?.length ? weatherCondition($language, weatherState.weatherCode, weatherState.weatherDescription) : $t('Waiting for current weather')}</span>
        {#if weatherState.nodes?.length}<span class="wind">{format(weatherState.windSpeedKmh, wholeNumber)} km/h · {compass(weatherState.windDirectionDeg, $language)}</span>{/if}
      </div>
      <span class="compact-clock" aria-hidden={expanded}>{compactClockLabel}</span>
    </div>
    <div class="metrics-wrap" aria-hidden={!expanded}>
      <div class="metrics">
        <span>{$t('Cloud cover')} <b>{format(weatherState.cloudCoverPct, wholeNumber)}%</b></span>
        <span>{$t('Rain')} <b>{format(weatherState.precipitationMmH, decimalNumber)} <small>mm/h</small></b></span>
      </div>
    </div>
  </button>
  <div id="weather-dashboard-content" class="dashboard-body" aria-hidden={!expanded} inert={!expanded}>
    <div class="dashboard-inner">
      <time class="weather-clock" datetime={currentTime.toISOString()} aria-label={$t('Current Rotterdam date and time')}><span>{dateLabel}</span><strong>{clockLabel}</strong></time>
      <div class="source-line">
        <span>Model · {timeLabel(weatherState.validAt, compactClockFormat)}</span>
        {#if weatherState.radarAt}
          <a href="https://www.rainviewer.com/" target="_blank" rel="noreferrer">Radar {timeLabel(weatherState.radarAt, compactClockFormat)} · RainViewer</a>
        {:else}<span>{$t(weatherState.radarEnabled ? 'Radar unavailable' : 'Radar off')}</span>{/if}
      </div>
      <details class="weather-details">
        <summary>{$t('Source & weather notes')}<span aria-hidden="true">+</span></summary>
        <div class="notes-content">
          <div class="detail-row"><span>{$t('Source')}</span><span>KNMI via Open-Meteo</span></div>
          <div class="detail-row"><span>{$t('Model valid at')}</span><span>{timeLabel(weatherState.validAt, compactClockFormat)} · {$t('Rotterdam time')}</span></div>
          <p>{$t('Model conditions for Rotterdam Centrum. The Aerial map shows model clouds that fade as you zoom into the streets.')}</p>
          <p>{$t('Rain intensity is a model estimate. The radar overlay shows observed precipitation.')}</p>
          {#if weatherState.status === 'stale'}<p>{$t('These values are outdated. Weather effects resume when fresh data returns.')}</p>{/if}
          <button class="refresh" on:click={() => weatherController?.refreshLive()}>{$t('Refresh weather')} <span aria-hidden="true">↻</span></button>
        </div>
      </details>
    </div>
  </div>
</aside>

<style>
  .weather-hud { position:fixed; top:24px; right:24px; z-index:120; width:154px; max-width:calc(100vw - 32px); max-height:calc(100dvh - 48px); box-sizing:border-box; overflow:auto; scrollbar-width:thin; background:#171a19fa; color:#efeee7; border:1px solid #ffffff20; border-radius:4px; box-shadow:0 8px 32px #0002; font:12px 'Instrument Sans','Helvetica Neue',Arial,sans-serif; animation:weather-in .8s .15s cubic-bezier(.16,1,.3,1) both; transition:width .4s cubic-bezier(.16,1,.3,1); }
  .weather-hud.expanded { width:288px; }
  button { font:inherit; color:inherit; cursor:pointer; }
  .weather-summary { display:block; width:100%; padding:12px 14px 10px; border:0; background:none; text-align:left; transition:background .2s,padding .4s; }
  .expanded .weather-summary { padding:17px 18px 15px; }
  .weather-summary:hover { background:#ffffff03; }
  .heading { display:flex; justify-content:space-between; gap:8px; align-items:center; font-size:9px; letter-spacing:1.1px; color:#c3c8bb; }
  .heading-label { white-space:nowrap; }
  .weather-location { display:inline-block; max-width:0; opacity:0; overflow:hidden; vertical-align:bottom; color:#8b9780; transition:max-width .4s,opacity .2s; }
  .expanded .weather-location { max-width:80px; opacity:1; }
  .status { display:flex; align-items:center; gap:5px; letter-spacing:0; font-size:10px; color:#adb99f; white-space:nowrap; }
  .status i { width:4px; height:4px; border-radius:50%; background:#a8b899; flex-shrink:0; }
  .weather-hud:not(.expanded) .heading-label { display:none; }
  .weather-hud:not(.expanded) .status { width:100%; }
  .weather-hud:not(.expanded) .chevron { margin-left:auto; }
  .chevron { font-size:15px; margin-left:3px; transition:transform .35s; }
  .chevron.open { transform:rotate(180deg); }
  .conditions { display:flex; align-items:center; gap:0; padding:8px 0 0; transition:padding .4s,gap .4s; }
  .expanded .conditions { gap:16px; padding:15px 0 16px; }
  .temperature { font-size:29px; font-weight:400; letter-spacing:-1.7px; line-height:1; font-variant-numeric:tabular-nums; flex-shrink:0; transition:font-size .4s,letter-spacing .4s; }
  .temperature small { font-size:.72em; vertical-align:top; }
  .expanded .temperature { font-size:43px; letter-spacing:-2.7px; }
  .condition-copy { display:grid; gap:7px; width:0; min-width:0; max-height:0; opacity:0; overflow:hidden; font-size:12px; line-height:1.3; transition:width .4s,max-height .4s,opacity .2s; }
  .expanded .condition-copy { width:160px; max-height:64px; opacity:1; }
  .wind { font-size:11px; color:#9eac90; white-space:nowrap; }
  .compact-clock { margin-left:auto; font-size:10px; color:#a8b89b; font-variant-numeric:tabular-nums; transition:opacity .2s; }
  .expanded .compact-clock { display:none; }
  .metrics-wrap { display:grid; grid-template-rows:0fr; transition:grid-template-rows .4s cubic-bezier(.16,1,.3,1); }
  .expanded .metrics-wrap { grid-template-rows:1fr; }
  .metrics { min-height:0; overflow:hidden; display:flex; justify-content:space-between; gap:14px; font-size:10px; color:#a3af95; opacity:0; transition:opacity .2s,padding .4s; }
  .expanded .metrics { opacity:1; padding-top:12px; border-top:1px solid #ffffff17; }
  .metrics b { color:#e0e7d6; font-size:12px; font-weight:500; margin-left:4px; }
  .metrics small { font-size:10px; color:#a3af95; }
  .dashboard-body { display:grid; grid-template-rows:0fr; visibility:hidden; transition:grid-template-rows .4s cubic-bezier(.16,1,.3,1),visibility .4s; }
  .expanded .dashboard-body { grid-template-rows:1fr; visibility:visible; }
  .dashboard-inner { min-height:0; overflow:hidden; }
  .weather-clock { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:13px 18px; border-top:1px solid #ffffff17; color:#b6c1aa; font-size:11px; white-space:nowrap; }
  .weather-clock strong { color:#e0e6d7; font-size:11px; font-weight:500; font-variant-numeric:tabular-nums; }
  .source-line { display:flex; justify-content:space-between; gap:8px; padding:9px 18px; background:#b0c09806; border-top:1px solid #ffffff09; font-size:9px; color:#9eac90; }
  .source-line a { color:inherit; text-decoration:none; }
  .source-line a:hover { text-decoration:underline; }
  .weather-details { border-top:1px solid #ffffff16; font-size:12px; line-height:1.7; }
  .weather-details>summary { display:flex; align-items:center; justify-content:space-between; padding:12px 18px; color:#aab89d; font-size:10px; cursor:pointer; list-style:none; }
  .weather-details>summary::-webkit-details-marker { display:none; }
  .weather-details>summary>span { color:#c3d1b4; font-size:16px; transition:transform .25s; }
  .weather-details[open]>summary>span { transform:rotate(45deg); }
  .notes-content { padding:0 18px 17px; }
  .detail-row { display:flex; justify-content:space-between; gap:12px; margin-bottom:9px; font-size:11px; color:#c4cfb8; }
  .detail-row>span:first-child { color:#a1ae94; }
  .weather-details p { margin:14px 0; color:#a6b398; }
  .refresh { display:flex; align-items:center; justify-content:space-between; gap:14px; width:100%; padding:12px; border:1px solid #b3c39e44; background:#bdcca60b; border-radius:2px; color:#d1dec2; text-align:left; transition:background .2s; }
  .refresh:hover { background:#bdcca61a; }
  .refresh span { font-size:18px; }
  button:focus-visible,a:focus-visible,summary:focus-visible { outline:2px solid #c8d4b9; outline-offset:-3px; }
  @keyframes weather-in { from { opacity:0; transform:translateY(12px); } to { opacity:1; transform:translateY(0); } }
  @media(max-width:700px) { .weather-hud { top:17px; right:16px; width:120px; max-height:calc(100dvh - 34px); } .weather-hud.expanded { width:calc(100vw - 32px); } }
  @media(max-width:360px) { .weather-hud:not(.expanded) { width:98px; } .weather-hud:not(.expanded) .weather-summary { padding:11px 10px; } .weather-hud:not(.expanded) .status { font-size:9px; gap:4px; } .weather-hud:not(.expanded) .compact-clock { font-size:8px; } .weather-hud:not(.expanded) .temperature { font-size:27px; } }
  @media(prefers-reduced-motion:reduce) { *,*::before,*::after { animation:none!important; transition:none!important; } }
</style>
