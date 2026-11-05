<script>
  import { onMount, onDestroy, tick } from 'svelte';
  import { fly, fade } from 'svelte/transition';
  import { createMapDataController } from './mapDataController.js';
  import { MAP_DATASETS, DATASET_BY_ID, featureTitle, featureSubtitle, normalizeFeature, geometryBounds, intersectsBounds, formatDate } from './explorerData.js';
  import { API_BASE_URL } from './liveLayers.js';
  import { resetView } from './map.js';
  import ExplorerIcon from './ExplorerIcon.svelte';
  import MapAppearance from './MapAppearance.svelte';
  import FeatureDetails from './FeatureDetails.svelte';
  export let map;
  export let weatherController = null;
  export let weatherState = {};
  export let apiStatus = 'connecting';
  let controller;
  let layers = {};
  let tab = 'layers';
  let viewMode = typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('mode') || 'satellite' : 'satellite';
  let placeLabels = true;
  let buildingHeights = false;
  let query = '';
  let results = [];
  let searching = false;
  let searchError = false;
  let searchTimer;
  let searchAbort;
  let searchInput;
  let searchResultsEl;
  let mobileTrigger;
  let desktopTrigger;
  let desktopOpen = true;
  let isMobile = false;
  let selected = null;
  let selectionOrigin = null;
  let restoreMobile = false;
  let focusedLayer = null;
  let listLimit = 40;
  let reduceMotion = false;
  let mobileOpen = false;
  const mobile = () => window.matchMedia('(max-width: 700px)').matches;
  $: panelVisible = isMobile ? mobileOpen : desktopOpen;
  $: activeCount = Object.keys(layers).length;
  $: if (focusedLayer && !layers[focusedLayer]) focusedLayer = null;
  $: activeFeatures = focusedLayer ? layers[focusedLayer]?.features || [] : Object.values(layers).flatMap(layer => layer.features);
  $: visibleItems = activeFeatures.slice(0, listLimit);
  $: isLoading = Object.values(layers).some(layer => layer.status === 'loading');
  $: isLimited = Object.values(layers).some(layer => layer.truncated);
  $: failedLayers = Object.entries(layers).filter(([, layer]) => ['error', 'stale'].includes(layer.status));
  $: selectedLayer = layers[selected?.properties.__dataset];
  onMount(() => {
    const breakpoint = window.matchMedia('(max-width: 700px)');
    isMobile = breakpoint.matches;
    const viewportChanged = event => isMobile = event.matches;
    breakpoint.addEventListener('change', viewportChanged);
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    reduceMotion = preference.matches;
    const motionChanged = event => reduceMotion = event.matches;
    preference.addEventListener('change', motionChanged);
    controller = createMapDataController(map, value => layers = value, feature => {
      selected = feature;
      if (feature) selectionOrigin = document.activeElement;
      if (feature && mobile()) { restoreMobile = mobileOpen; mobileOpen = false; }
    });
    const shortcuts = async event => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); controller?.select(null); restoreMobile = false; mobileOpen = mobile(); desktopOpen = true; await tick(); searchInput?.focus();
      }
      if (event.key === 'Escape') {
        if (selected) closeSelection();
        else if (query) { query = ''; search(); searchInput?.focus(); }
        else if (mobileOpen) { mobileOpen = false; mobileTrigger?.focus(); }
        else if (!isMobile && desktopOpen) { desktopOpen = false; desktopTrigger?.focus(); }
      }
    };
    window.addEventListener('keydown', shortcuts);
    return () => { breakpoint.removeEventListener('change', viewportChanged); preference.removeEventListener('change', motionChanged); window.removeEventListener('keydown', shortcuts); };
  });
  onDestroy(() => { controller?.destroy(); clearTimeout(searchTimer); searchAbort?.abort(); });
  function canFocus(feature) {
    const limit = map.getMaxBounds();
    return !limit || intersectsBounds(feature, [limit.getWest(), limit.getSouth(), limit.getEast(), limit.getNorth()]);
  }
  function moveTo(feature) {
    if (!canFocus(feature)) return;
    const box = geometryBounds(feature.geometry);
    if (!box) return;
    const duration = reduceMotion ? 0 : 900;
    if (feature.geometry.type === 'Point') map.flyTo({ center: feature.geometry.coordinates, zoom: Math.max(14, map.getZoom()), offset: mobile() ? [0, -90] : [130, 0], duration, essential: false });
    else map.fitBounds([[box[0], box[1]], [box[2], box[3]]], { padding: mobile() ? { top: 140, bottom: 280, left: 35, right: 35 } : { top: 100, bottom: 100, left: 390, right: 80 }, duration, maxZoom: 14 });
  }
  function focus(feature) {
    selectionOrigin = document.activeElement;
    controller?.select(feature);
    moveTo(feature);
  }
  async function closeSelection() {
    controller?.select(null);
    if (restoreMobile && mobile()) mobileOpen = true;
    restoreMobile = false;
    await tick();
    if (selectionOrigin?.isConnected) selectionOrigin.focus();
    else if (mobile()) mobileTrigger?.focus();
    else searchInput?.focus();
  }
  function toggleLayer(id) {
    controller?.toggle(id);
    if (focusedLayer === id && !layers[id]) focusedLayer = null;
  }
  function search() {
    clearTimeout(searchTimer); searchAbort?.abort(); searchAbort = null;
    results = []; searchError = false;
    searching = query.trim().length >= 2;
    if (!searching) return;
    const value = query.trim();
    const abort = new AbortController(); searchAbort = abort;
    searchTimer = setTimeout(async () => {
      const timeout = setTimeout(() => abort.abort(), 12000);
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/search?q=${encodeURIComponent(value)}&limit=8`, { signal: abort.signal });
        if (!response.ok) throw new Error();
        const data = await response.json();
        if (data.type !== 'FeatureCollection' || !Array.isArray(data.features)) throw new Error();
        if (searchAbort === abort) results = data.features.filter(feature => geometryBounds(feature.geometry)).map(feature => normalizeFeature(feature));
      } catch (_) { if (searchAbort === abort) searchError = true; }
      finally { clearTimeout(timeout); if (searchAbort === abort) searching = false; }
    }, 300);
  }
  function setTab(value) { tab = value; listLimit = 40; }
  function toggleExplorer() {
    const opening = !mobileOpen;
    if (opening) { controller?.select(null); restoreMobile = false; }
    mobileOpen = opening;
  }
</script>

<div class="city-shell">
  <header class="identity"><span class="brand-mark" aria-hidden="true">r<span>.</span></span><div><strong>rotterdam<span>live</span></strong><p>A city, unfolding.</p></div></header>
  <button class="mobile-trigger" bind:this={mobileTrigger} on:click={toggleExplorer} aria-expanded={mobileOpen} aria-controls="city-explorer">{mobileOpen ? 'Back to the map' : 'Explore the city'}<span>{activeCount ? `${activeCount} layers` : '+'}</span></button>
  <button class="desktop-trigger" bind:this={desktopTrigger} aria-label={desktopOpen ? 'Hide explorer' : 'Show explorer'} title={desktopOpen ? 'Hide explorer' : 'Show explorer'} aria-expanded={desktopOpen} aria-controls="city-explorer" on:click={() => desktopOpen = !desktopOpen}><ExplorerIcon name="layers" size={18}/>{#if activeCount}<span>{activeCount}</span>{/if}</button>
  <aside id="city-explorer" class="explorer" class:desktop-collapsed={!desktopOpen && !isMobile} class:mobile-open={mobileOpen} aria-hidden={!panelVisible} inert={!panelVisible} aria-label="City explorer">
    <div class="intro"><span class="eyebrow">YOUR WINDOW INTO THE CITY</span><h1>Find your<br/><em>Rotterdam.</em></h1><p>Follow the everyday rhythm.<br/>Choose what you want to see.</p></div>
    <div class="search-box"><ExplorerIcon name="search" size={16}/><input bind:this={searchInput} aria-label="Search Rotterdam" aria-controls="place-search-results" placeholder="A street, a place, a moment…" bind:value={query} on:input={search} on:keydown={event => {if (event.key === 'ArrowDown' && results.length) {event.preventDefault(); searchResultsEl?.querySelector('button')?.focus();}}}/>{#if query}<button aria-label="Clear search" on:click={() => {query = ''; search(); searchInput?.focus();}}><ExplorerIcon name="close" size={13}/></button>{:else}<kbd aria-hidden="true">⌘ K</kbd>{/if}</div>
    {#if query.trim().length >= 2}
      <div id="place-search-results" class="search-results" bind:this={searchResultsEl} aria-label="Search results" aria-live="polite">
        {#if searching}<p>Finding your place…</p>{:else if searchError}<p>Search is unavailable. <button class="text-button" on:click={search}>Try again</button></p>{:else if !results.length}<p>No places found. Try another name.</p>{/if}
        {#each results as result}<button class="search-result" on:click={() => {focus(result); query = ''; search();}}><strong>{featureTitle(result)}</strong><small>{featureSubtitle(result)}</small><span><ExplorerIcon name="arrow" size={13}/></span></button>{/each}
      </div>
    {/if}
    <nav class="tabs" aria-label="Explorer sections"><button class:active={tab === 'layers'} aria-pressed={tab === 'layers'} on:click={() => setTab('layers')}>Map layers <span>{activeCount.toString().padStart(2, '0')}</span></button><button class:active={tab === 'activity'} aria-pressed={tab === 'activity'} on:click={() => setTab('activity')}>In view <span>{activeFeatures.length}</span></button><button class:active={tab === 'map'} aria-pressed={tab === 'map'} on:click={() => setTab('map')}>Map <ExplorerIcon name="compass" size={13}/></button></nav>
    <div class="panel-content">
      {#if tab === 'layers'}
        <div in:fade={{duration: reduceMotion ? 0 : 180}}>
          {#if !activeCount}<p class="layer-guidance">Start with one layer. Add more as you explore.</p>{/if}
          {#each ['Discover', 'Move', 'Live city'] as group}
            <div class="group-title">{group}</div>
            {#each MAP_DATASETS.filter(dataset => dataset.group === group) as dataset}
              <div class="layer-block" class:chosen={layers[dataset.id]}>
                <button class="layer-row" aria-label={dataset.label} aria-pressed={!!layers[dataset.id]} on:click={() => toggleLayer(dataset.id)}>
                  <span class="layer-symbol" style={`--layer-color:${dataset.color}`}><ExplorerIcon name={dataset.icon} size={16}/></span>
                  <span class="layer-copy"><strong>{dataset.label}</strong><small>{layers[dataset.id]?.status === 'loading' ? 'Updating this part of the city…' : layers[dataset.id]?.status === 'error' ? 'Feed temporarily unavailable' : layers[dataset.id]?.status === 'stale' ? 'Last available data · refresh failed' : layers[dataset.id] ? `${layers[dataset.id].features.length} in this view` : dataset.caption}</small></span>
                  <span class="toggle" aria-hidden="true"><i></i></span>
                </button>
                {#if layers[dataset.id]}
                  <div class="layer-options" in:fly={{y:-3,duration:reduceMotion ? 0 : 170}}>
                    {#each dataset.filters || [] as filter}
                      <label><span>{filter.label}</span><select aria-label={`${dataset.label}: ${filter.label}`} value={layers[dataset.id].filters[filter.key] || ''} on:change={event => controller?.setFilters(dataset.id, {[filter.key]: event.currentTarget.value})}>{#each filter.options as [value,label]}<option {value}>{label}</option>{/each}</select></label>
                    {/each}
                    {#if ['error','stale'].includes(layers[dataset.id].status)}<p class="feed-error">{layers[dataset.id].error} <button on:click={() => controller?.retry(dataset.id)}>Retry {dataset.label}</button></p>{/if}
                    {#if layers[dataset.id].truncated}<p class="limit-note">Up to 150 loaded here. Zoom in for a smaller selection.</p>{/if}
                    {#if ['crowd','traffic'].includes(dataset.id)}<div class="legend"><span>{dataset.id === 'crowd' ? 'Quiet' : 'Free flow'}</span><i style="background:#9dac8c"></i><i style="background:#c2b18d"></i><i style="background:#b18e79"></i><i style="background:#a77670"></i><span>{dataset.id === 'crowd' ? 'Busy · estimate' : 'Delayed'}</span></div>{/if}
                    <button class="browse-layer" on:click={() => {focusedLayer = dataset.id; setTab('activity');}}>Explore {dataset.label.toLowerCase()}<ExplorerIcon name="arrow" size={11}/></button>
                  </div>
                {/if}
              </div>
            {/each}
          {/each}
        </div>
      {:else if tab === 'activity'}
        <div in:fade={{duration: reduceMotion ? 0 : 180}}>
          <div class="activity-heading"><span>{isLoading ? 'Updating your view…' : 'Selected layers · current view'}</span><span>{activeFeatures.length} places & reports</span></div>
          {#if activeCount}<div class="filter-chips" aria-label="Filter results by layer"><button class:current={!focusedLayer} aria-pressed={!focusedLayer} on:click={() => {focusedLayer = null; listLimit = 40;}}>All</button>{#each Object.keys(layers) as id}<button class:current={focusedLayer === id} aria-pressed={focusedLayer === id} on:click={() => {focusedLayer = id; listLimit = 40;}}>{DATASET_BY_ID[id].label}</button>{/each}</div>{/if}
          {#each failedLayers as [id,layer]}<p class="feed-error">{DATASET_BY_ID[id].label}: {layer.status === 'stale' ? 'showing last available records' : 'currently unavailable'}. <button on:click={() => controller?.retry(id)}>Retry</button></p>{/each}
          {#if !activeCount}<div class="empty-state"><span>Start with a little curiosity.</span><p>Add a map layer to discover what’s happening around you.</p><button on:click={() => setTab('layers')}>Choose a layer ↗</button></div>{:else if isLoading && !visibleItems.length}<div class="skeleton-list" aria-label="Loading results"><i></i><i></i><i></i></div>{:else if !visibleItems.length}<div class="empty-state"><span>Nothing in this view yet.</span><p>Move the map, change a filter, or try another layer. New results appear when you stop moving.</p></div>{/if}
          {#each visibleItems as feature, index (`${feature.properties.__dataset}-${feature.id || feature.properties.id || index}`)}<button class="result-row" on:click={() => focus(feature)}><strong>{featureTitle(feature)}</strong><small>{featureSubtitle(feature)}</small><span><ExplorerIcon name="arrow" size={13}/></span>{#if feature.properties.start_time}<time>{formatDate(feature.properties.start_time)}</time>{/if}</button>{/each}
          {#if activeFeatures.length > listLimit}<button class="load-more" on:click={() => listLimit += 40}>Show more in this view <span>+{Math.min(40,activeFeatures.length - listLimit)}</span></button>{/if}
          {#if isLimited}<p class="limit-note">Some layers have more records. Zoom in to explore a smaller area.</p>{/if}
        </div>
      {:else}
        <div in:fade={{duration: reduceMotion ? 0 : 180}}><MapAppearance {map} {weatherController} {weatherState} bind:mode={viewMode} bind:labels={placeLabels} bind:buildings={buildingHeights}/></div>
      {/if}
    </div>
    <footer><span class="connection" class:offline={apiStatus === 'offline'} aria-live="polite"><i></i>{apiStatus === 'offline' ? 'API disconnected · retrying' : apiStatus === 'connecting' ? 'Connecting to the city…' : isLoading ? 'Updating selected layers…' : activeCount ? `${activeCount} selected · minute updates` : 'Your map. Your pace.'}</span>{#if activeCount}<button on:click={() => {controller?.clear(); controller?.select(null);}}>Clear all</button>{:else}<span class="coordinates">51.92° N</span>{/if}</footer>
  </aside>
  <div class="map-tools" class:mobile-covered={mobileOpen || !!selected} aria-label="Map navigation"><button aria-label="Zoom in" on:click={() => map.zoomIn({duration: reduceMotion ? 0 : 350})}>+</button><button aria-label="Zoom out" on:click={() => map.zoomOut({duration: reduceMotion ? 0 : 350})}>−</button><span></span><button aria-label="Reset map view" on:click={() => resetView(map)}><ExplorerIcon name="reset" size={17}/></button></div>
  <div class="map-note"><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap</a><span>{viewMode === 'satellite' ? 'Aerial imagery: PDOK · OpenFreeMap' : 'Cartography: OpenFreeMap'}</span></div>
  {#if selected}<FeatureDetails feature={selected} layerState={selectedLayer} reducedMotion={reduceMotion} canFocus={canFocus(selected)} explorerOpen={desktopOpen} onClose={closeSelection} onFocus={() => moveTo(selected)}/>{/if}
</div>
<style>

  .city-shell{
  --ink:#e4e3dd;
  --muted:#91968e;
  --edge:#ffffff13;
  position:absolute;
  inset:0;
  pointer-events:none;
  color:var(--ink);
  font:13px system-ui,sans-serif}
button,input{
  font:inherit;
  color:inherit}
button{
  cursor:pointer}
button:focus-visible,input:focus-visible{
  outline:2px solid #bfc8b4;
  outline-offset:3px}
button{
  transition:background .2s,color .2s,border-color .2s}
 .identity{
  position:absolute;
  top:27px;
  left:32px;
  display:flex;
  gap:13px;
  align-items:center;
  pointer-events:auto}
.brand-mark{
  font:italic 52px Georgia,serif;
  line-height:1}
.brand-mark span{
  color:#a7b69d}
.identity strong{
  font-size:19px;
  font-weight:550;
  letter-spacing:-.7px}
.identity strong span{
  font-weight:350;
  color:#aaa}
.identity p{
  margin:3px 0 0;
  color:#aeb5aa;
  font-size:10px;
  letter-spacing:1.5px}
.explorer{
  pointer-events:auto;
  position:absolute;
  left:24px;
  top:115px;
  bottom:28px;
  width:330px;
  display:flex;
  flex-direction:column;
  background:#191d1af5;
  border:1px solid var(--edge);
  border-radius:17px;
  box-shadow:0 15px 65px #0004;
  overflow:hidden;
  animation:arrive .65s cubic-bezier(.2,.7,.2,1) both}
.intro{
  padding:25px 25px 19px}
.eyebrow{
  font-size:8px;
  letter-spacing:1.8px;
  color:#a4ae9a}
.intro h1{
  font-size:38px;
  line-height:1.05;
  font-weight:450;
  letter-spacing:-1.7px;
  margin:17px 0 13px}
.intro em{
  font:italic 42px Georgia,serif;
  color:#c8cbbd}
.intro p{
  font-size:11px;
  line-height:1.7;
  color:var(--muted);
  margin:0}
.search-box{
  display:flex;
  gap:10px;
  align-items:center;
  border:1px solid #ffffff1b;
  background:#ffffff04;
  border-radius:8px;
  margin:0 20px 18px;
  padding:10px}
.search-box input{
  border:0;
  background:none;
  outline:none;
  width:100%;
  font-size:10px;
  min-width:0}
.search-box button{
  border:0;
  background:none;
  padding:0}
.tabs{
  display:flex;
  border-block:1px solid var(--edge);
  padding-inline:20px;
  gap:23px}
.tabs button{
  border:0;
  border-bottom:2px solid transparent;
  padding:13px 0;
  background:none;
  color:#959d91;
  font-size:11px}
.tabs button.active{
  color:#e4e7dd;
  border-bottom-color:#b6bea8}
.tabs span{
  margin-left:7px;
  font-size:9px;
  color:#818a7a}
.panel-content{
  overflow-y:auto;
  min-height:0;
  flex:1;
  padding:8px 12px 16px;
  scrollbar-width:thin;
  scrollbar-color:#41483b transparent}
.group-title{
  font-size:9px;
  text-transform:uppercase;
  letter-spacing:1.5px;
  color:#818b78;
  padding:17px 12px 9px}
.layer-row{
  display:flex;
  align-items:center;
  width:100%;
  gap:11px;
  text-align:left;
  padding:11px 10px;
  border:1px solid transparent;
  border-radius:9px;
  background:none}
.layer-row:hover{
  background:#ffffff05}
.layer-block.chosen{
  background:#bac4ad09;
  border-color:#b9c4ae1b}
.layer-symbol{
  display:grid;
  place-items:center;
  flex:0 0 29px;
  height:29px;
  border:1px solid #ffffff15;
  border-radius:8px;
  color:var(--layer-color);
  font:italic 17px Georgia,serif}
.layer-copy{
  display:grid;
  gap:4px;
  flex:1}
.layer-copy strong{
  font-weight:450;
  font-size:12px}
.layer-copy small{
  font-size:10px;
  color:#9ca591}
.toggle{
  width:26px;
  height:15px;
  border-radius:9px;
  background:#363d32;
  position:relative;
  flex-shrink:0}
.toggle i{
  position:absolute;
  top:3px;
  left:3px;
  width:9px;
  height:9px;
  border-radius:50%;
  background:#8e9786;
  transition:transform .25s,background .25s}
.chosen .toggle{
  background:#aebca4}
.chosen .toggle i{
  transform:translateX(11px);
  background:#252e23}
footer{
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:15px 20px;
  border-top:1px solid var(--edge);
  font-size:9px;
  color:#9ba48f}
footer i{
  display:inline-block;
  width:4px;
  height:4px;
  border-radius:50%;
  background:#a5b298;
  margin-right:5px}
footer button{
  font-size:9px;
  border:0;
  background:none;
  color:#c4ccba}
.coordinates{
  letter-spacing:1px}
.map-tools{
  pointer-events:auto;
  position:absolute;
  right:26px;
  bottom:63px;
  padding:5px;
  background:#1c211ded;
  border:1px solid var(--edge);
  border-radius:10px;
  display:grid}
.map-tools button{
  width:33px;
  height:34px;
  border:0;
  background:none;
  font-size:19px}
.map-tools button:hover{
  background:#ffffff0b}
.map-tools>span{
  height:1px;
  background:var(--edge);
  margin:4px}
.map-note{
  position:absolute;
  bottom:26px;
  right:26px;
  font-size:8px;
  letter-spacing:1.5px;
  color:#b3bcb1}
.map-note span{
  margin-left:20px;
  letter-spacing:0;
  color:#8c9789}
.search-results{
  margin:-10px 20px 15px;
  max-height:180px;
  overflow:auto;
  flex-shrink:0}
.search-results p{
  font-size:11px;
  color:var(--muted)}
.search-results .search-result,.result-row{
  display:grid;
  grid-template-columns:1fr auto;
  text-align:left;
  width:100%;
  border:0;
  border-bottom:1px solid var(--edge);
  background:none;
  padding:12px 8px;
  gap:4px}
.search-results strong,.result-row strong{
  font-size:11px;
  font-weight:450}
.search-results small,.result-row small{
  color:var(--muted);
  font-size:10px;
  grid-column:1}
.search-results span,.result-row span{
  grid-column:2;
  grid-row:1/3;
  color:#a4b097}
.activity-heading{
  display:flex;
  justify-content:space-between;
  font-size:9px;
  padding:15px 10px;
  color:var(--muted)}
.empty-state{
  padding:30px 15px}
.empty-state>span{
  font:22px Georgia,serif}
.empty-state p,.limit-note{
  color:var(--muted);
  line-height:1.7;
  font-size:11px}
.empty-state button{
  border:0;
  border-bottom:1px solid #a7b29866;
  background:none;
  padding:7px 0;
  color:#c6cebc;
  font-size:11px}
.mobile-trigger{
  display:none}
@keyframes arrive{
  from{
  opacity:0;
  transform:translateY(18px)}
to{
  opacity:1;
  transform:translateY(0)}
}
@media(max-height:800px) and (min-width:701px){
  .intro{
  padding:18px 25px 16px}
.intro h1{
  font-size:30px;
  margin:10px 0}
.intro em{
  font-size:33px}
.intro p{
  display:none}
.explorer{
  top:100px;
  bottom:20px}
}
@media(max-width:700px){
  .identity{
  top:20px;
  left:18px}
.identity strong{
  font-size:15px}
.brand-mark{
  font-size:36px}
.identity p{
  font-size:8px}
.explorer{
  top:auto;
  bottom:74px;
  left:12px;
  width:calc(100% - 24px);
  max-height:60dvh;
  display:none}
.explorer.mobile-open{
  display:flex}
.intro{
  display:none}
.search-box{
  margin:14px 16px}
.mobile-trigger{
  display:flex;
  position:absolute;
  bottom:22px;
  left:18px;
  right:70px;
  justify-content:space-between;
  pointer-events:auto;
  border:1px solid #ffffff25;
  background:#22281ff5;
  border-radius:11px;
  padding:14px 17px;
  font-size:12px}
.mobile-trigger span{
  color:#a9b89d}
.map-tools{
  right:14px;
  bottom:22px}
.map-tools button{
  height:27px;
  width:27px}
.map-tools>span,.map-tools button:last-child{
  display:none}
.map-note{
  display:none}
footer{
  padding:13px 20px}
.panel-content{
  max-height:38vh}
}
@media(prefers-reduced-motion:reduce){
  *{
  animation:none!important;
  transition:none!important}
}


  .layer-block {
   border: 1px solid transparent;
   border-radius: 10px;
   margin-bottom: 3px;
   }

  .layer-block.chosen {
   border-color: #b9c4ae1b;
   background: #bac4ad07;
   }

  .layer-options {
   padding: 0 12px 11px 49px;
   }

  .layer-options label {
   display: grid;
   gap: 6px;
   margin: 3px 0 10px;
   }

  .layer-options label > span {
   font-size: 9px;
   color: #9eab91;
   }

  select {
   width: 100%;
   padding: 8px;
   border: 1px solid #ffffff1b;
   border-radius: 6px;
   background: #252d22;
   color: #d5ddcc;
   font: 10px system-ui, sans-serif;
   color-scheme: dark;
   cursor: pointer;
   }

  .browse-layer {
   display: flex;
   justify-content: space-between;
   align-items: center;
   width: 100%;
   border: 0;
   background: none;
   padding: 8px 0 0;
   color: #c3cdb7;
   font-size: 9px;
   }

  .layer-guidance {
   padding: 6px 12px 0;
   color: #9ca88f;
   font-size: 10px;
   line-height: 1.7;
   }

  .feed-error {
   font-size: 10px;
   color: #c4b395;
   line-height: 1.7;
   padding: 7px 10px;
   margin: 8px 0;
   border-radius: 6px;
   background: #b8a8870a;
   }

  .feed-error button, .text-button {
   color: #d6cfba;
   font: inherit;
   padding: 0;
   border: 0;
   border-bottom: 1px solid #d6cfba66;
   background: none;
   }

  .legend {
   display: flex;
   align-items: center;
   gap: 4px;
   padding: 8px 0 3px;
   font-size: 8px;
   color: #a9b39e;
   }

  .legend i {
   width: 12px;
   height: 5px;
   border-radius: 1px;
   }

  .legend > span:first-child {
   margin-right: 5px;
   }

  .legend > span:last-child {
   margin-left: 5px;
   }

  .filter-chips {
   display: flex;
   flex-wrap: wrap;
   gap: 5px;
   padding: 0 9px 13px;
   }

  .filter-chips button {
   font-size: 9px;
   color: #a5b296;
   border: 1px solid #ffffff15;
   border-radius: 14px;
   padding: 6px 9px;
   background: #ffffff03;
   }

  .filter-chips button.current {
   background: #b1c09c18;
   border-color: #b1c09c55;
   color: #d7dfce;
   }

  .tabs {
   gap: 20px;
   }

  .tabs button {
   display: inline-flex;
   align-items: center;
   gap: 5px;
   }

  .tabs span {
   margin-left: 1px;
   }

  .tabs button :global(svg) {
   margin-left: 3px;
   }

  .search-box {
   flex-shrink: 0;
   }

  .search-box :global(svg) {
   flex-shrink: 0;
   }

  .search-box kbd {
   white-space: nowrap;
   font: 8px system-ui, sans-serif;
   color: #78876d;
   }

  .search-box > button {
   display: flex;
   }

  .load-more {
   display: flex;
   justify-content: space-between;
   width: calc(100% - 20px);
   margin: 16px 10px;
   padding: 10px 12px;
   border: 1px solid #ffffff20;
   border-radius: 7px;
   background: #ffffff03;
   color: #c5d0b9;
   font-size: 11px;
   }

  .result-row {
   padding: 15px 10px;
   border-radius: 6px;
   }

  .result-row:hover, .search-result:hover {
   background: #b9c7a60a;
   }

  .result-row time {
   color: #8e9f80;
   font-size: 9px;
   padding-top: 5px;
   }

  .connection.offline {
   color: #c3ac8b;
   }

  .connection.offline i {
   background: #c3ac8b;
   }

  .map-tools button {
   display: grid;
   place-items: center;
   }

  .map-note {
   pointer-events: auto;
   letter-spacing: 0;
   }

  .map-note a {
   color: inherit;
   text-decoration: none;
   }

  .map-note a:hover {
   text-decoration: underline;
   }

  .skeleton-list {
   display: grid;
   gap: 12px;
   padding: 18px 12px;
   }

  .skeleton-list i {
   display: block;
   height: 50px;
   background: linear-gradient(100deg,#ffffff03,#ffffff08,#ffffff03);
   background-size: 200% 100%;
   border-radius: 7px;
   animation: shimmer 1.5s infinite;
   }

  @keyframes shimmer {
   to {
   background-position: -200% 0;
   }
 }

  @media(max-width:700px) {
   .map-tools {
   right: 12px;
   bottom: 18px;
   }
 .map-tools button {
   width: 34px;
   height: 32px;
   }
 .explorer {
   bottom: 80px;
   }
 .search-box kbd {
   display: none;
   }
 .panel-content {
   max-height: 43dvh;
   }
 }



  .identity { background: #1b221ce8; border: 1px solid #ffffff12; border-radius: 12px; padding: 8px 16px; top: 21px; left: 24px; }
  @media (max-width:700px) { .identity { padding: 8px 10px; top: 16px; left: 12px; } .map-tools button { width: 38px; height: 38px; } .map-tools { bottom: 26px; } .mobile-trigger { right: 75px; } }

  @media(max-height:560px) and (min-width:701px) { .intro { display:none; } .explorer { top:85px; bottom:14px; } .search-box { margin-top:14px; } .identity { top:12px; padding:6px 12px; } .brand-mark { font-size:36px; } }

  .city-shell { z-index: 10; }
  @media(max-width:700px) { .map-tools { bottom:54px; } .map-tools.mobile-covered { display:none; } }

  .desktop-trigger { position:absolute; left:306px; top:32px; pointer-events:auto; display:grid; place-items:center; width:42px; height:42px; padding:0; background:#1b221ced; border:1px solid #ffffff20; border-radius:10px; color:#c6d0bb; }
  .desktop-trigger:hover { background:#303b29; }
  .desktop-trigger > span { position:absolute; right:-4px; top:-5px; background:#b4c1a3; color:#1b2416; border-radius:10px; min-width:15px; padding:2px; font-size:8px; }
  .explorer.desktop-collapsed { animation:none; opacity:0; visibility:hidden; pointer-events:none; transform:translateX(-18px); }
  @media(max-width:700px) { .desktop-trigger { display:none; } }
  @media(max-height:560px) and (min-width:701px) { .desktop-trigger { top:19px; } }
</style>
