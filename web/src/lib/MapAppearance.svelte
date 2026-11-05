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
  function loaded() { if (!changing) return; changing = false; styleMessage = ''; clearTimeout(styleTimer); clearTimeout(settleTimer); settleTimer = null; toggleLabels(map, labels); toggle3DBuildings(map, buildings); }
  function styleChanged() {
    if (changing && !settleTimer) settleTimer = setTimeout(loaded, 250);
  }
  onMount(() => { map.on('style.load', loaded); map.on('styledata', styleChanged); });
  onDestroy(() => { clearTimeout(styleTimer); clearTimeout(settleTimer); map.off('style.load', loaded); map.off('styledata', styleChanged); });
  function chooseMode(value) {
    if (mode === value) return;
    mode = value; changing = true; styleMessage = '';
    clearTimeout(styleTimer); clearTimeout(settleTimer); settleTimer = null;
    styleTimer = setTimeout(() => { changing = false; styleMessage = 'Some map tiles are taking longer to load.'; }, 10000);
    try { switchStyle(map, value, { labels, buildings3d: buildings }); }
    catch { clearTimeout(styleTimer); changing = false; styleMessage = 'Could not change the map. Try another view.'; }
    const url = new URL(window.location.href); url.searchParams.set('mode', value); window.history.replaceState(null, '', url);
  }
</script>
<div class="appearance">
  <span class="section-label">A DIFFERENT PERSPECTIVE</span>
  <h2>Make it your map.</h2>
  <p>Choose a view, then set the details.</p>
  <div class="view-options" aria-label="Base map">
    {#each [{id:'satellite',label:'Aerial',description:'The city from above'}, {id:'dark',label:'Night',description:'Quiet, considered detail'}, {id:'clean',label:'Atlas',description:'A clear view of the streets'}] as view}
      <button class:active={mode === view.id} aria-pressed={mode === view.id} on:click={() => chooseMode(view.id)}><span class="preview {view.id}"><i></i><b></b><em></em></span><strong>{view.label}</strong></button>
    {/each}
  </div>
  <div class="style-status" aria-live="polite">{changing ? 'Changing perspective…' : styleMessage || 'Your selected data layers stay on the map.'}</div>
  <div class="preference"><div><strong>Place names</strong><small>Street and neighbourhood labels</small></div><button class="toggle" class:enabled={labels} role="switch" aria-checked={labels} aria-label="Place names" on:click={() => {labels = !labels; toggleLabels(map, labels);}}><i></i></button></div>
  <div class="preference"><div><strong>Building heights</strong><small>Visible when you zoom into the city</small></div><button class="toggle" class:enabled={buildings} role="switch" aria-checked={buildings} aria-label="Building heights" on:click={() => {buildings = !buildings; toggle3DBuildings(map, buildings);}}><i></i></button></div>
  <div class="divider"></div>
  <div class="preference"><div><strong>Cloud atmosphere</strong><small>Model-driven clouds and soft shadows</small></div><button class="toggle" class:enabled={weatherState?.enabled} role="switch" aria-checked={!!weatherState?.enabled} aria-label="Cloud atmosphere" on:click={() => weatherController?.setEnabled(!weatherState?.enabled)}><i></i></button></div>
  <div class="preference"><div><strong>Rain radar</strong><small>Latest observed rain · loads when enabled</small></div><button class="toggle" class:enabled={weatherState?.radarEnabled} role="switch" aria-checked={!!weatherState?.radarEnabled} aria-label="Rain radar" on:click={() => weatherController?.setRadarEnabled(!weatherState?.radarEnabled)}><i></i></button></div>
  {#if weatherState?.radarEnabled && !weatherState?.radarAt}<p class="hint">A recent radar frame isn’t available yet. We’ll try again automatically.</p>{/if}
  <div class="map-guidance"><ExplorerIcon name="compass" size={23}/><div><strong>A little room to explore.</strong><p>Scroll to zoom. Drag to move. Hold Ctrl and drag to change your angle, or use two fingers on a trackpad.</p></div></div>
  <p class="attribution">Map data © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> · <a href="https://openfreemap.org/" target="_blank" rel="noreferrer">OpenFreeMap</a><br/>Aerial imagery: <a href="https://www.pdok.nl/" target="_blank" rel="noreferrer">PDOK</a></p>
</div>
<style>
  .appearance { padding: 23px 12px; } .section-label{font-size:9px;letter-spacing:1.5px;color:#aab59d} h2{font:25px Georgia,serif;letter-spacing:-.5px;margin:12px 0 8px}p{font-size:11px;color:#a0aa96;line-height:1.7;margin:0 0 20px}.view-options{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}button{font:inherit;color:inherit;cursor:pointer}.view-options button{padding:4px 4px 10px;background:#ffffff03;border:1px solid #ffffff16;border-radius:9px;text-align:left;transition:background .2s,border-color .2s}.view-options button.active{border-color:#b1bca5;background:#b1bca50a}.view-options strong{display:block;margin:8px 5px 0;font-weight:450;font-size:11px}.preview{display:block;position:relative;height:60px;border-radius:5px;overflow:hidden;background:#2b3730}.preview i,.preview b,.preview em{position:absolute;display:block}.preview i{height:150%;width:17%;background:#50625c;transform:rotate(33deg);left:35%;top:-20%}.preview b{height:130%;width:1px;background:#88876c;transform:rotate(-30deg);left:70%;top:-20%;box-shadow:-18px 0 #88876c,18px 0 #88876c}.preview em{height:1px;width:150%;background:#88876c;transform:rotate(20deg);left:-25%;top:70%;box-shadow:0 -14px #88876c,0 14px #88876c}.preview.dark{background:#171d1a}.preview.dark i{background:#25342e}.preview.dark b,.preview.dark em{opacity:.5}.preview.clean{background:#c1c3af}.preview.clean i{background:#9aacaa}.preview.clean b,.preview.clean em{background:#e3e0ce}.preview.satellite{background:repeating-linear-gradient(65deg,#343f2b 0px,#343f2b 7px,#565b42 8px,#414b33 13px)}.style-status{min-height:30px;font-size:9px;line-height:1.6;color:#9ba78e;margin:12px 0}.preference{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 0}.preference strong,.preference small{display:block}.preference strong{font-size:12px;font-weight:450}.preference small{font-size:10px;color:#9aa58f;margin-top:5px}.toggle{border:0;position:relative;width:30px;height:18px;border-radius:10px;background:#3a4235;flex-shrink:0;padding:0}.toggle i{position:absolute;left:3px;top:3px;width:12px;height:12px;border-radius:50%;background:#929f86;transition:transform .25s}.toggle.enabled{background:#aebd9d}.toggle.enabled i{transform:translateX(12px);background:#273123}.divider{border-top:1px solid #ffffff14;margin:15px 0}.map-guidance{display:flex;gap:12px;border:1px solid #ffffff13;border-radius:10px;margin-top:24px;padding:16px;color:#b8c1ad}.map-guidance strong{font-size:11px;font-weight:500}.map-guidance p{font-size:10px;margin:7px 0 0}.map-guidance :global(svg){flex-shrink:0;margin-top:3px}.hint{font-size:10px}.attribution{font-size:9px;margin:25px 0 0;color:#8e9a82}.attribution a{color:inherit;text-underline-offset:3px}button:focus-visible,a:focus-visible{outline:2px solid #c1ccb5;outline-offset:3px}@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
