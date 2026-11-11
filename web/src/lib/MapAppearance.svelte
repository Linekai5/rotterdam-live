<script>
  import { onMount, onDestroy } from 'svelte';
  import { switchStyle, toggleLabels, toggle3DBuildings } from './map.js';
  import ExplorerIcon from './ExplorerIcon.svelte';
  export let map;
  export let weatherController;
  export let weatherState;
  export let mode = typeof window === 'undefined' ? 'satellite' : new URLSearchParams(window.location.search).get('mode') || 'satellite';
  export let labels = true;
  export let buildings = false;
  let changing = false;
  let styleTimer;
  let settleTimer;
  let styleMessage = '';
  const views = [{id:'satellite',label:'Aerial',description:'The city from above'}, {id:'dark',label:'Night',description:'A quieter street map'}, {id:'clean',label:'Atlas',description:'Clear cartographic detail'}];
  function loaded() { if (!changing) return; changing = false; styleMessage = ''; clearTimeout(styleTimer); clearTimeout(settleTimer); settleTimer = null; toggleLabels(map, labels); toggle3DBuildings(map, buildings); }
  function styleChanged() {
    if (changing && !settleTimer) settleTimer = setTimeout(loaded, 250);
  }
  onMount(() => { map.on('style.load', loaded); map.on('styledata', styleChanged); });
  onDestroy(() => { clearTimeout(styleTimer); clearTimeout(settleTimer); map.off('style.load', loaded); map.off('styledata', styleChanged); });
  function chooseMode(value) {
    if (mode === value) return;
    const previousMode = mode;
    mode = value; changing = true; styleMessage = '';
    clearTimeout(styleTimer); clearTimeout(settleTimer); settleTimer = null;
    styleTimer = setTimeout(() => { changing = false; styleMessage = 'Some map tiles are taking longer to load.'; }, 10000);
    try { switchStyle(map, value, { labels, buildings3d: buildings }); }
    catch { mode = previousMode; clearTimeout(styleTimer); changing = false; styleMessage = 'Could not change the map. Try another view.'; return; }
    const url = new URL(window.location.href); url.searchParams.set('mode', value); window.history.replaceState(null, '', url);
  }
</script>
<div class="appearance">
  <div class="section-kicker"><span>YOUR PERSPECTIVE</span><span aria-hidden="true">03 / VIEWS</span></div>
  <h2>Shape your view.</h2>
  <p class="introduction">Three ways to read Rotterdam.</p>
  <div class="view-options" aria-label="Base map">
    {#each views as view, index}
      <button class:active={mode === view.id} aria-label={view.label} aria-pressed={mode === view.id} on:click={() => chooseMode(view.id)}>
        <span class="preview {view.id}">
          <svg viewBox="0 0 96 82" fill="none" aria-hidden="true">
            <g class="city-blocks"><path d="M5 7h18v12H5zM29 5h21v16H29zM57 2h18v13H57zM79 7h14v20H79zM5 27h17v12H5zM29 28h16v8H29zM60 23h15v13H60zM11 64h15v12H11zM32 62h17v16H32zM58 61h17v15H58zM80 55h15v20H80z"/></g>
            <g class="streets"><path d="M-4 20 102 39M-4 35 102 54M22-5 4 89M43-5 23 89M68-5 48 89M91-5 72 89"/><path d="M-5 9 99 77M-3 79 101 8"/></g>
            <path class="river-edge" d="M-8 53c24-16 40 10 58 0S79 26 104 35"/>
            <path class="river" d="M-8 53c24-16 40 10 58 0S79 26 104 35"/>
            <g class="bridge"><path d="m51 39 9 20M53 39l9 19M54 44l5 5-2-8m-1 8 5 5-2-7"/></g>
            <g class="map-reference"><path d="M7 7h5M7 7v5M89 70v5h-5"/></g>
          </svg>
          <span class="view-number">0{index + 1}</span>
        </span>
        <span class="view-label"><strong>{view.label}</strong><svg class="view-check" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m3 8 3 3 7-7"/></svg></span>
      </button>
    {/each}
  </div>
  <div class="style-status" class:changing aria-live="polite"><span aria-hidden="true">{changing ? '↻' : '↳'}</span>{changing ? 'Changing perspective…' : styleMessage || 'Selected data stays with you.'}</div>
  <div class="control-heading"><span>MAP DETAILS</span><span aria-hidden="true">01</span></div>
  <div class="preference"><div><strong>Place names</strong><small>Streets & neighbourhood labels</small></div><button class="toggle" class:enabled={labels} role="switch" aria-checked={labels} aria-label="Place names" on:click={() => {labels = !labels; toggleLabels(map, labels);}}><i></i></button></div>
  <div class="preference"><div><strong>Building heights</strong><small>Explore the city in three dimensions</small></div><button class="toggle" class:enabled={buildings} role="switch" aria-checked={buildings} aria-label="Building heights" on:click={() => {buildings = !buildings; toggle3DBuildings(map, buildings);}}><i></i></button></div>
  <div class="control-heading atmosphere-heading"><span>LIVE ATMOSPHERE</span><span aria-hidden="true">02</span></div>
  <div class="preference"><div><strong>Cloud atmosphere</strong><small>{weatherState?.status === 'live' && weatherState?.cloudCoverPct === 0 ? 'Current model: clear over Centrum' : 'Model-driven clouds & soft shadows'}</small></div><button class="toggle" class:enabled={weatherState?.enabled} role="switch" aria-checked={!!weatherState?.enabled} aria-label="Cloud atmosphere" on:click={() => weatherController?.setEnabled(!weatherState?.enabled)}><i></i></button></div>
  <div class="preference"><div><strong>Rain radar</strong><small>Latest observed rain · loads on request</small></div><button class="toggle" class:enabled={weatherState?.radarEnabled} role="switch" aria-checked={!!weatherState?.radarEnabled} aria-label="Rain radar" on:click={() => weatherController?.setRadarEnabled(!weatherState?.radarEnabled)}><i></i></button></div>
  {#if weatherState?.radarEnabled && !weatherState?.radarAt}<p class="hint" role="status">A recent radar frame isn’t available yet. We’ll try again automatically.</p>{/if}
  <div class="map-guidance"><span class="guidance-icon"><ExplorerIcon name="compass" size={25}/></span><div><strong>A change of angle.</strong><p>Scroll to zoom. Drag to move. Hold Ctrl and drag to tilt and turn the map.</p></div></div>
  <section class="attribution" aria-label="Map credits">
    <h3>Map credits</h3>
    <p>Map data © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a> · <a href="https://openfreemap.org/" target="_blank" rel="noopener noreferrer">OpenFreeMap</a></p>
    <p>Aerial imagery, 2026: <a href="https://www.beeldmateriaal.nl/" target="_blank" rel="noopener noreferrer">Samenwerkingsverband Beeldmateriaal</a> / <a href="https://www.pdok.nl/" target="_blank" rel="noopener noreferrer">PDOK</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">CC BY 4.0</a> (water blended).</p>
  </section>
</div>
<style>
  .appearance { padding:25px 5px 9px; }
  .section-kicker { display:flex; align-items:center; justify-content:space-between; font-size:9px; letter-spacing:1.4px; color:#b9c5ac; }
  .section-kicker>span+span { font-size:9px; letter-spacing:.7px; color:#7f8a79; }
  h2 { font-size:29px; font-weight:450; line-height:1.1; letter-spacing:-1.1px; margin:16px 0 10px; }
  p { font-size:12px; color:#9ea898; line-height:1.7; }
  .introduction { margin:0 0 24px; }
  button { font:inherit; color:inherit; cursor:pointer; }
  .view-options { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:9px; }
  .view-options button { position:relative; padding:3px; background:#ffffff02; border:1px solid #ffffff16; border-radius:3px 12px 3px 3px; text-align:left; transition:border-color .25s,background .25s; }
  .view-options button:hover { background:#ffffff06; border-color:#b9c5ac66; }
  .view-options button.active { border-color:#b9c5ac; background:#b9c5ac0a; }
  .preview { position:relative; display:block; height:83px; overflow:hidden; border-radius:1px 9px 0 0; background:#2e342c; }
  .preview>svg { display:block; width:100%; height:100%; transition:transform .65s cubic-bezier(.2,.7,.2,1); }
  .view-options button:hover .preview>svg { transform:scale(1.09) rotate(-2deg); }
  .city-blocks { fill:#525842; }
  .city-blocks path { stroke:#2d3427; stroke-width:.5; }
  .streets { stroke:#a5aa8d; stroke-width:1; opacity:.45; }
  .streets path+path { stroke-width:2; }
  .river-edge { stroke:#707e6d; stroke-width:17; }
  .river { stroke:#3b5350; stroke-width:13; }
  .bridge { stroke:#d8d5bb; stroke-width:.8; }
  .map-reference { stroke:#d8dfcd; stroke-width:.65; opacity:.65; }
  .preview.dark { background:#1b211e; }
  .dark .city-blocks { fill:#293129; }
  .dark .city-blocks path { stroke:#1d241e; }
  .dark .streets { stroke:#8b977f; opacity:.4; }
  .dark .river-edge { stroke:#1a2824; }
  .dark .river { stroke:#14221f; }
  .preview.clean { background:#c1c4b5; }
  .clean .city-blocks { fill:#e0dfd1; }
  .clean .city-blocks path { stroke:#bfc6b6; }
  .clean .streets { stroke:#f0eee6; opacity:1; }
  .clean .river-edge { stroke:#92a69e; }
  .clean .river { stroke:#a4b9b1; }
  .clean .bridge,.clean .map-reference { stroke:#6f7b67; }
  .view-number { position:absolute; bottom:6px; right:7px; color:#dde2d1; font-size:9px; letter-spacing:1px; }
  .clean .view-number { color:#5c6753; }
  .view-label { display:flex; align-items:center; justify-content:space-between; gap:4px; padding:11px 7px 9px; }
  .view-label strong { font-size:12px; font-weight:450; }
  .view-check { width:14px; height:14px; stroke:#bdcbaa; stroke-width:1.5; opacity:0; transition:opacity .2s; }
  .view-check path { stroke-dasharray:16; stroke-dashoffset:16; transition:stroke-dashoffset .35s cubic-bezier(.2,.7,.2,1); }
  .active .view-check { opacity:1; }
  .active .view-check path { stroke-dashoffset:0; }
  .style-status { display:flex; align-items:center; gap:8px; min-height:38px; margin:8px 0 14px; color:#98a28f; font-size:11px; line-height:1.5; }
  .style-status>span { display:inline-block; color:#b9c5ac; font-size:16px; }
  .style-status.changing>span { animation:rotate-status 1.2s linear infinite; }
  .control-heading { display:flex; justify-content:space-between; border-top:1px solid #ffffff1c; padding:19px 0 5px; color:#9ba88f; font-size:9px; letter-spacing:1.3px; }
  .control-heading>span+span { color:#718069; font-variant-numeric:tabular-nums; }
  .atmosphere-heading { margin-top:13px; }
  .preference { display:flex; align-items:center; justify-content:space-between; gap:13px; padding:13px 0; }
  .preference strong,.preference small { display:block; }
  .preference strong { font-size:13px; font-weight:450; color:#e0e5d8; }
  .preference small { font-size:11px; color:#959f8d; margin-top:5px; line-height:1.5; }
  .toggle { position:relative; width:35px; height:21px; border:1px solid #ffffff22; border-radius:5px; background:#323a2c; flex-shrink:0; padding:0; transition:background .25s,border-color .25s; }
  .toggle::before { content:''; position:absolute; inset:-12px -8px; }
  .toggle i { position:absolute; left:3px; top:3px; width:13px; height:13px; border-radius:2px; background:#819273; transition:transform .3s cubic-bezier(.2,.7,.2,1),background .25s; }
  .toggle.enabled { background:#b9c5ac; border-color:#b9c5ac; }
  .toggle.enabled i { transform:translateX(14px); background:#273021; }
  .map-guidance { display:flex; gap:14px; border-top:1px solid #ffffff1c; border-bottom:1px solid #ffffff1c; margin-top:25px; padding:20px 0; color:#bdc7b3; }
  .guidance-icon { display:flex; flex-shrink:0; margin-top:3px; }
  .map-guidance strong { font-size:12px; font-weight:450; color:#e0e5d8; }
  .map-guidance p { font-size:11px; margin:7px 0 0; }
  .hint { font-size:11px; border-left:2px solid #bdaf8e; padding-left:12px; margin:7px 0 15px; }
  .attribution { margin:21px 0 0; color:#a1af94; }
  .attribution h3 { margin:0 0 10px; font-size:11px; font-weight:500; color:#c1cdb5; }
  .attribution p { margin:8px 0 0; font-size:11px; color:inherit; line-height:1.8; }
  .attribution a { color:inherit; text-underline-offset:3px; }
  button:focus-visible,a:focus-visible { outline:2px solid #d4dfc7; outline-offset:3px; }
  @keyframes rotate-status { to { transform:rotate(360deg); } }
  @media(prefers-reduced-motion:reduce) { *,*::before,*::after { transition:none!important; animation:none!important; } }
</style>
