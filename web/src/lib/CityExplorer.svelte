<script>
  import { onMount, onDestroy, tick } from 'svelte';
  import { fly, slide } from 'svelte/transition';
  import { quintOut } from 'svelte/easing';
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
  let tabDirection = 1;
  let category = 'All';
  let hovered = null;
  let currentTime = new Date();
  let camera = { lng: 4.48, lat: 51.92, zoom: 11 };
  let panelContent;
  let scrollMore = false;
  function updateScrollCue() { if (panelContent) scrollMore = panelContent.scrollHeight - panelContent.clientHeight - panelContent.scrollTop > 24; }
  function trackOverflow(node) { const observer = new ResizeObserver(updateScrollCue); observer.observe(node); return { destroy: () => observer.disconnect() }; }
  const categories = ['All', 'Discover', 'Move', 'Live city'];
  const sourceType = id => ['districts', 'retail', 'amenities', 'cameras'].includes(id) ? 'Directory' : id === 'events' ? 'Agenda' : id === 'crowd' ? 'Model estimate' : 'Source feed';
  $: dateLabel = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', timeZone: 'Europe/Amsterdam' }).format(currentTime);
  $: clockLabel = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Amsterdam', timeZoneName: 'short' }).format(currentTime);
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
    }, value => hovered = value);
    const updateCamera = () => { const center = map.getCenter(); camera = { lng: center.lng, lat: center.lat, zoom: map.getZoom() }; hovered = null; };
    map.on('moveend', updateCamera);
    updateCamera();
    const clockTimer = setInterval(() => currentTime = new Date(), 30000);
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
    return () => { clearInterval(clockTimer); map.off('moveend', updateCamera); breakpoint.removeEventListener('change', viewportChanged); preference.removeEventListener('change', motionChanged); window.removeEventListener('keydown', shortcuts); };
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
  function setTab(value) { tabDirection = ['layers', 'activity', 'map'].indexOf(value) >= ['layers', 'activity', 'map'].indexOf(tab) ? 1 : -1; tab = value; listLimit = 40; }
  function toggleExplorer() {
    const opening = !mobileOpen;
    if (opening) { controller?.select(null); restoreMobile = false; }
    mobileOpen = opening;
  }
</script>

<div class="city-shell">
  <header class="identity"><svg class="brand-mark" viewBox="0 0 42 38" fill="none" aria-hidden="true"><path d="M4 31h34M10 31 25 4l5 27M25 4 20 31M25 4l12 24M25 4 5 28" stroke="currentColor" stroke-width="1.3"/><path d="M5 28h32" stroke="currentColor" stroke-width="3"/></svg><div><strong>rotterdam<span>live</span></strong><p>AN OPEN WINDOW ON THE CITY</p></div></header>
  <div class="city-time"><span>ROTTERDAM, NL</span><time>{dateLabel}<i></i>{clockLabel}</time></div>
  <button class="mobile-trigger" bind:this={mobileTrigger} on:click={toggleExplorer} aria-expanded={mobileOpen} aria-controls="city-explorer">{mobileOpen ? 'Back to the map' : 'Explore the city'}<span>{activeCount ? `${activeCount} layers` : '+'}</span></button>
  <button class="desktop-trigger" bind:this={desktopTrigger} aria-label={desktopOpen ? 'Hide explorer' : 'Show explorer'} title={desktopOpen ? 'Hide explorer' : 'Show explorer'} aria-expanded={desktopOpen} aria-controls="city-explorer" on:click={() => desktopOpen = !desktopOpen}><ExplorerIcon name="layers" size={18}/>{#if activeCount}<span>{activeCount}</span>{/if}</button>
  <aside id="city-explorer" class="explorer" class:desktop-collapsed={!desktopOpen && !isMobile} class:mobile-open={mobileOpen} aria-hidden={!panelVisible} inert={!panelVisible} aria-label="City explorer">
    <div class="intro"><span class="eyebrow"><span class="section-index">01 /</span> THE CITY AT YOUR FINGERTIPS</span><h1 aria-label="Explore Rotterdam."><span>Explore </span><span>Rotterdam<span class="title-dot">.</span></span></h1><p>A closer look at what moves the city.</p></div>
    <div class="search-box"><ExplorerIcon name="search" size={17}/><input bind:this={searchInput} aria-label="Search Rotterdam" aria-controls="place-search-results" placeholder="Find a street or a place" bind:value={query} on:input={search} on:keydown={event => {if (event.key === 'ArrowDown' && results.length) {event.preventDefault(); searchResultsEl?.querySelector('button')?.focus();}}}/>{#if query}<button aria-label="Clear search" on:click={() => {query = ''; search(); searchInput?.focus();}}><ExplorerIcon name="close" size={13}/></button>{:else}<kbd aria-hidden="true">⌘ K</kbd>{/if}</div>
    {#if query.trim().length >= 2}
      <div id="place-search-results" class="search-results" bind:this={searchResultsEl} aria-label="Search results" aria-live="polite">
        {#if searching}<p>Finding your place…</p>{:else if searchError}<p>Search is unavailable. <button class="text-button" on:click={search}>Try again</button></p>{:else if !results.length}<p>No places found. Try another name.</p>{/if}
        {#each results as result}<button class="search-result" on:click={() => {focus(result); query = ''; search();}}><strong>{featureTitle(result)}</strong><small>{featureSubtitle(result)}</small><span><ExplorerIcon name="arrow" size={13}/></span></button>{/each}
      </div>
    {/if}
    <nav class="tabs" aria-label="Explorer sections" style={`--tab:${['layers','activity','map'].indexOf(tab)}`}><span class="tab-indicator" aria-hidden="true"></span><button class:active={tab === 'layers'} aria-pressed={tab === 'layers'} on:click={() => setTab('layers')}>Map layers <span>{activeCount.toString().padStart(2, '0')}</span></button><button class:active={tab === 'activity'} aria-pressed={tab === 'activity'} on:click={() => setTab('activity')}>In view <span>{activeFeatures.length}</span></button><button class:active={tab === 'map'} aria-pressed={tab === 'map'} on:click={() => setTab('map')}>Map <ExplorerIcon name="compass" size={13}/></button></nav>
    <div class="panel-content" bind:this={panelContent} use:trackOverflow on:scroll={updateScrollCue}>
      {#key tab}<div class="tab-page" use:trackOverflow in:fly={{x:tabDirection*18,duration:reduceMotion ? 0 : 360,easing:quintOut}}>
      {#if tab === 'layers'}
        <div>
          <div class="category-nav" aria-label="Layer categories">{#each categories as item}<button class:current={category === item} aria-pressed={category === item} on:click={() => category = item}>{item === 'Live city' ? 'City' : item}</button>{/each}</div>
          <p class="layer-guidance">{activeCount ? `${activeCount} layers on your map. Select another to add it.` : 'Choose a layer. Build your own view.'}</p>
          {#each ['Discover', 'Move', 'Live city'].filter(group => category === 'All' || category === group) as group (group)}
            <section class="dataset-group" in:slide={{duration:reduceMotion ? 0 : 320,easing:quintOut}}>
            <div class="group-title"><span>{group}</span><span>{MAP_DATASETS.filter(dataset => dataset.group === group).length.toString().padStart(2,'0')}</span></div>
            {#each MAP_DATASETS.filter(dataset => dataset.group === group) as dataset,index (dataset.id)}
              <div class="layer-block" class:chosen={layers[dataset.id]} style={`--row:${index}`}>
                <button class="layer-row" aria-label={dataset.label} aria-pressed={!!layers[dataset.id]} on:click={() => toggleLayer(dataset.id)}>
                  <span class="layer-symbol" style={`--layer-color:${dataset.color}`}><ExplorerIcon name={dataset.icon} size={22}/></span>
                  <span class="layer-copy"><strong>{dataset.label}</strong><small>{layers[dataset.id]?.status === 'loading' ? 'Updating this part of the city…' : layers[dataset.id]?.status === 'error' ? 'Feed temporarily unavailable' : layers[dataset.id]?.status === 'stale' ? 'Last available data · refresh failed' : layers[dataset.id] ? `${layers[dataset.id].features.length} in this view` : dataset.caption}</small></span>
                  <span class="toggle" aria-hidden="true"><span></span><span></span></span>
                </button>
                {#if layers[dataset.id]}
                  <div class="layer-options" transition:slide={{duration:reduceMotion ? 0 : 320,easing:quintOut}}>
                    {#each dataset.filters || [] as filter}
                      <label><span>{filter.label}</span><select aria-label={`${dataset.label}: ${filter.label}`} value={layers[dataset.id].filters[filter.key] || ''} on:change={event => controller?.setFilters(dataset.id, {[filter.key]: event.currentTarget.value})}>{#each filter.options as [value,label]}<option {value}>{label}</option>{/each}</select></label>
                    {/each}
                    {#if ['error','stale'].includes(layers[dataset.id].status)}<p class="feed-error">{layers[dataset.id].error} <button on:click={() => controller?.retry(dataset.id)}>Retry {dataset.label}</button></p>{/if}
                    {#if layers[dataset.id].status === 'ready' && !layers[dataset.id].features.length}<p class="empty-feed">No {dataset.label.toLowerCase()} in this view. Try another category or move the map.</p>{/if}
                    {#if dataset.id === 'cameras'}<p class="camera-note">Mapped locations from OpenStreetMap. This source does not provide public video.</p>{/if}
                    <div class="source-kind">{sourceType(dataset.id)}<span>{dataset.source}</span></div>
                    {#if layers[dataset.id].truncated}<p class="limit-note">Up to 150 loaded here. Zoom in for a smaller selection.</p>{/if}
                    {#if ['crowd','traffic'].includes(dataset.id)}<div class="legend"><span>{dataset.id === 'crowd' ? 'Quiet' : 'Free flow'}</span><i style="background:#9dac8c"></i><i style="background:#c2b18d"></i><i style="background:#b18e79"></i><i style="background:#a77670"></i><span>{dataset.id === 'crowd' ? 'Busy · estimate' : 'Delayed'}</span></div>{/if}
                    <button class="browse-layer" on:click={() => {focusedLayer = dataset.id; setTab('activity');}}>Explore {dataset.label.toLowerCase()}<ExplorerIcon name="arrow" size={11}/></button>
                  </div>
                {/if}
              </div>
            {/each}
            </section>
          {/each}
        </div>
      {:else if tab === 'activity'}
        <div>
          <div class="activity-heading"><span>{isLoading ? 'Updating your view…' : 'Selected layers · current view'}</span><span>{activeFeatures.length} places & reports</span></div>
          {#if activeCount}<div class="filter-chips" aria-label="Filter results by layer"><button class:current={!focusedLayer} aria-pressed={!focusedLayer} on:click={() => {focusedLayer = null; listLimit = 40;}}>All</button>{#each Object.keys(layers) as id}<button class:current={focusedLayer === id} aria-pressed={focusedLayer === id} on:click={() => {focusedLayer = id; listLimit = 40;}}>{DATASET_BY_ID[id].label}</button>{/each}</div>{/if}
          {#each failedLayers as [id,layer]}<p class="feed-error">{DATASET_BY_ID[id].label}: {layer.status === 'stale' ? 'showing last available records' : 'currently unavailable'}. <button on:click={() => controller?.retry(id)}>Retry</button></p>{/each}
          {#if !activeCount}<div class="empty-state"><ExplorerIcon name="layers" size={36}/><span>Your city. Your perspective.</span><p>Select a map layer to see places and reports in the current view.</p><button on:click={() => setTab('layers')}>Choose a layer <ExplorerIcon name="arrow" size={14}/></button></div>{:else if isLoading && !visibleItems.length}<div class="skeleton-list" aria-label="Loading results"><i></i><i></i><i></i></div>{:else if !visibleItems.length}<div class="empty-state"><span>Nothing in this view yet.</span><p>Move the map, change a filter, or try another layer. New results appear when you stop moving.</p></div>{/if}
          {#each visibleItems as feature, index (`${feature.properties.__dataset}-${feature.id || feature.properties.id || index}`)}<button class="result-row" style={`--row:${Math.min(index,8)}`} on:click={() => focus(feature)}><span class="result-symbol"><ExplorerIcon name={DATASET_BY_ID[feature.properties.__dataset]?.icon || 'pin'} size={19}/></span><strong>{featureTitle(feature)}</strong><small>{featureSubtitle(feature)}</small><span class="result-arrow"><ExplorerIcon name="arrow" size={14}/></span>{#if feature.properties.start_time}<time>{formatDate(feature.properties.start_time)}</time>{/if}</button>{/each}
          {#if activeFeatures.length > listLimit}<button class="load-more" on:click={() => listLimit += 40}>Show more in this view <span>+{Math.min(40,activeFeatures.length - listLimit)}</span></button>{/if}
          {#if isLimited}<p class="limit-note">Some layers have more records. Zoom in to explore a smaller area.</p>{/if}
        </div>
      {:else}
        <div><MapAppearance {map} {weatherController} {weatherState} bind:mode={viewMode} bind:labels={placeLabels} bind:buildings={buildingHeights}/></div>
      {/if}
      </div>{/key}
    </div>
    <div class="scroll-cue" class:shown={scrollMore} aria-hidden="true">More below <span>↓</span></div>
    <footer><span class="connection" class:offline={apiStatus === 'offline'} aria-live="polite"><i></i>{apiStatus === 'offline' ? 'Connection lost · retrying' : apiStatus === 'connecting' ? 'Connecting…' : isLoading ? 'Updating selected layers…' : activeCount ? `${activeCount} selected · minute updates` : 'Connected to city data'}</span>{#if activeCount}<button on:click={() => {controller?.clear(); controller?.select(null);}}>Clear all</button>{:else}<span class="coordinates">{MAP_DATASETS.length} LAYERS</span>{/if}</footer>
  </aside>
  <div class="map-tools" class:mobile-covered={mobileOpen || !!selected} aria-label="Map navigation"><button aria-label="Zoom in" on:click={() => map.zoomIn({duration: reduceMotion ? 0 : 350})}>+</button><button aria-label="Zoom out" on:click={() => map.zoomOut({duration: reduceMotion ? 0 : 350})}>−</button><span></span><button aria-label="Reset map view" on:click={() => resetView(map)}><ExplorerIcon name="reset" size={17}/></button></div>
  <div class="map-note"><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap</a><span>{viewMode === 'satellite' ? 'Aerial imagery: PDOK · OpenFreeMap' : 'Cartography: OpenFreeMap'}</span></div>
  <div class="view-coordinates"><span class="crosshair">+</span><span>{camera.lat.toFixed(3)}° N&nbsp; / &nbsp;{camera.lng.toFixed(3)}° E</span><span class="view-mode">{viewMode === 'satellite' ? 'AERIAL' : viewMode === 'dark' ? 'NIGHT' : 'ATLAS'}</span></div>
  {#if hovered && !selected}<div class="map-tooltip" style={`left:${Math.max(12,Math.min(hovered.point.x + 18, (map.getContainer()?.clientWidth || 1200) - 265))}px;top:${Math.max(12,Math.min(hovered.point.y - 16,(map.getContainer()?.clientHeight || 900) - 160))}px`}><span>{DATASET_BY_ID[hovered.feature.properties.__dataset]?.label || 'Location'}</span><strong>{featureTitle(hovered.feature)}</strong><small>Select to explore ↗</small></div>{/if}
  {#if selected}<FeatureDetails feature={selected} layerState={selectedLayer} reducedMotion={reduceMotion} canFocus={canFocus(selected)} explorerOpen={desktopOpen} onClose={closeSelection} onFocus={() => moveTo(selected)}/>{/if}
</div>
<style>
  .city-shell { --explorer-width:354px; --explorer-inset:24px; --ink:#efeee7; --muted:#a1a79f; --edge:#ffffff19; --surface:#171a19; --accent:#bdc9b0; position:absolute; inset:0; z-index:10; pointer-events:none; color:var(--ink); font:13px 'Instrument Sans','Helvetica Neue',Arial,sans-serif; }
  button,input,select { font:inherit; color:inherit; } button { cursor:pointer; }
  button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
  button { transition:background .2s,color .2s,border-color .2s,transform .3s cubic-bezier(.2,.8,.2,1); }
  .identity { position:absolute; top:24px; left:24px; display:flex; align-items:center; gap:12px; pointer-events:auto; padding:9px 15px 9px 11px; background:#171a19f5; border:1px solid var(--edge); border-radius:3px; animation:interface-in .75s cubic-bezier(.16,1,.3,1) both; }
  .brand-mark { width:37px; height:36px; color:#e5e8dc; }
  .identity strong { font-weight:600; font-size:22px; letter-spacing:-1.1px; } .identity strong span { font-weight:400; color:#b2c09f; margin-left:1px; }
  .identity p { margin:4px 0 0; font-size:8px; letter-spacing:1.5px; color:#a0a79b; }
  .city-time { position:absolute; top:37px; left:calc(var(--explorer-inset) + var(--explorer-width) + 30px); display:flex; gap:24px; align-items:center; padding:10px 14px; background:#171a19e8; border-left:1px solid #b5c3a04a; font-size:10px; letter-spacing:1.2px; color:#e7e8df; animation:interface-in .8s .1s both; }
  .city-time>span { font-weight:600; } .city-time time { display:flex; align-items:center; gap:10px; color:#afb4a8; font-variant-numeric:tabular-nums; } .city-time i { height:3px; width:3px; background:#aab59b; border-radius:50%; }
  .desktop-trigger { position:absolute; left:336px; top:33px; pointer-events:auto; width:42px; height:42px; display:grid; place-items:center; border:1px solid var(--edge); border-radius:3px; background:#171a19f5; color:#d6ddcc; }
  .desktop-trigger:hover { background:#30372d; transform:translateY(-2px); } .desktop-trigger>span { position:absolute; top:-6px; right:-6px; padding:2px 5px; min-width:10px; font-size:9px; color:#1a2017; background:var(--accent); border-radius:2px; }
  .explorer { position:absolute; left:var(--explorer-inset); top:104px; bottom:90px; width:var(--explorer-width); pointer-events:auto; display:flex; flex-direction:column; overflow:hidden; background:#171a19fa; border:1px solid var(--edge); border-radius:4px; box-shadow:0 12px 40px #0003; animation:interface-in .8s .08s cubic-bezier(.16,1,.3,1) both; transition:transform .55s cubic-bezier(.16,1,.3,1),opacity .3s,visibility .4s; }
  .explorer.desktop-collapsed { animation:none; opacity:0; visibility:hidden; pointer-events:none; transform:translateX(-35px); }
  .intro { position:relative; padding:25px 25px 21px; border-bottom:1px solid #ffffff08; overflow:hidden; flex-shrink:0; }
  .eyebrow { display:block; font-size:9px; font-weight:500; letter-spacing:1.3px; color:#b3b8aa; } .section-index { margin-right:8px; color:#6d7868; }
  .intro h1 { font-size:33px; line-height:1.08; letter-spacing:-1.5px; font-weight:500; margin:17px 0 10px; position:relative; z-index:1; }
  .intro h1>span { display:inline-block; animation:title-in 1s cubic-bezier(.16,1,.3,1) both; } .intro h1>span:nth-child(2) { margin-left:5px; animation-delay:.12s; }
  .title-dot { color:var(--accent); } .intro p { margin:0; font-size:12px; color:#a9b0a1; }
  .search-box { display:flex; align-items:center; gap:11px; margin:19px 22px 17px; padding:12px 0; border-bottom:1px solid #85917870; flex-shrink:0; color:#c3cdb8; transition:border-color .25s; }
  .search-box:focus-within { border-color:#e1e7d9; } .search-box input { background:none; border:0; outline:none; min-width:0; width:100%; font-size:12px; color:#e6e8df; } .search-box input::placeholder { color:#9aa291; } .search-box :global(svg) { flex-shrink:0; }
  .search-box button { display:flex; border:0; padding:0; background:none; } .search-box kbd { font:9px inherit; color:#9ba48f; white-space:nowrap; border:1px solid var(--edge); border-radius:3px; padding:3px 4px; }
  .search-results { flex-shrink:0; max-height:260px; overflow:auto; margin:0 20px 14px; padding:3px 10px; background:#242923; border:1px solid var(--edge); } .search-results p { font-size:12px; line-height:1.6; color:var(--muted); }
  .search-result { position:relative; display:block; width:100%; padding:13px 22px 13px 0; border:0; border-bottom:1px solid var(--edge); background:none; text-align:left; } .search-result strong { display:block; font-size:13px; font-weight:500; } .search-result small { display:block; margin-top:5px; font-size:11px; color:var(--muted); } .search-result>span { position:absolute; right:0; top:16px; }
  .tabs { position:relative; display:grid; grid-template-columns:repeat(3,1fr); margin:0 22px; border-bottom:1px solid var(--edge); flex-shrink:0; }
  .tabs button { display:flex; align-items:center; justify-content:center; gap:7px; position:relative; padding:14px 0; border:0; background:none; color:#9ba491; font-size:12px; } .tabs button.active { color:#f1f1e9; } .tabs button>span { font-size:10px; color:#a3af97; font-variant-numeric:tabular-nums; }
  .tab-indicator { position:absolute; left:0; bottom:-1px; width:33.333%; height:2px; background:var(--accent); transform:translateX(calc(var(--tab)*100%)); transition:transform .5s cubic-bezier(.16,1,.3,1); }
  .panel-content { flex:1; min-height:0; overflow:auto; padding:0 12px 18px; scrollbar-width:thin; scrollbar-color:#56614d transparent; overscroll-behavior:contain; }
  .scroll-cue { display:flex; justify-content:space-between; align-items:center; flex-shrink:0; height:0; overflow:hidden; padding:0 20px; color:#aebd9f; background:#1c211b; font-size:9px; letter-spacing:.3px; pointer-events:none; opacity:0; transition:opacity .2s,height .25s; } .scroll-cue.shown { height:24px; opacity:1; } .scroll-cue>span { margin-left:6px; }
  .tab-page { min-height:100%; } .category-nav { display:flex; gap:4px; margin:19px 10px 0; } .category-nav button { padding:6px 10px; border:1px solid transparent; background:none; color:#9aa58e; font-size:11px; border-radius:2px; } .category-nav button.current { color:#edf0e5; border-color:#c1ccb239; background:#c1ccb20a; }
  .layer-guidance { margin:17px 13px 23px; font-size:11px; color:#a5b197; line-height:1.6; } .group-title { display:flex; justify-content:space-between; margin:24px 13px 9px; padding-bottom:9px; font-size:10px; text-transform:uppercase; letter-spacing:1.6px; color:#9ca78f; border-bottom:1px solid var(--edge); } .group-title>span:last-child { font-size:9px; letter-spacing:0; color:#75816d; }
  .layer-block { margin:0 3px; border-bottom:1px solid #ffffff08; transition:background .3s; animation:row-in .5s calc(var(--row)*35ms) cubic-bezier(.16,1,.3,1) both; } .layer-block.chosen { background:#b4c29f09; border-radius:3px; border-bottom-color:#b4c29f20; }
  .layer-row { display:flex; align-items:center; gap:13px; width:100%; padding:15px 10px; border:0; background:none; text-align:left; } .layer-row:hover { background:#ffffff04; } .layer-row:active { transform:scale(.985); }
  .layer-symbol { display:grid; place-items:center; width:38px; height:39px; flex-shrink:0; color:#c3ccb9; border:1px solid #aebaa02b; clip-path:polygon(0 0,calc(100% - 7px) 0,100% 7px,100% 100%,0 100%); background:#b4bfaa06; transition:background .35s,color .35s,transform .4s; } .chosen .layer-symbol { background:#c1ccb2; color:#252c20; border-color:#c1ccb2; }
  .layer-row:hover .layer-symbol { transform:translateY(-2px); } .layer-copy { flex:1; min-width:0; } .layer-copy strong { display:block; font-size:13px; font-weight:500; letter-spacing:.05px; } .layer-copy small { display:block; font-size:10px; line-height:1.5; color:#a0ab95; margin-top:5px; }
  .toggle { position:relative; width:20px; height:20px; display:block; flex-shrink:0; border:1px solid #9ba78f42; border-radius:2px; transition:background .3s,border-color .3s,transform .4s; }
  .toggle span { position:absolute; height:1px; width:8px; top:9px; left:5px; background:#a9b59d; transition:transform .35s,opacity .3s; } .toggle span:nth-child(2) { transform:rotate(90deg); } .chosen .toggle { background:#bec9b0; border-color:#bec9b0; } .chosen .toggle span { background:#232b1d; } .chosen .toggle span:nth-child(2) { transform:rotate(0); opacity:0; }
  .layer-options { padding:0 13px 14px 61px; } .layer-options label { display:block; margin:5px 0 13px; } .layer-options label>span { display:block; font-size:10px; color:#acb69f; margin-bottom:6px; }
  .layer-options select { display:block; width:100%; background:#242a21; border:1px solid #b7c5a735; border-radius:3px; padding:9px 8px; font-size:12px; color:#e0e7d7; color-scheme:dark; cursor:pointer; }
  .source-kind { font-size:9px; text-transform:uppercase; letter-spacing:.7px; color:#a1ad93; line-height:1.7; } .source-kind span { display:block; text-transform:none; letter-spacing:0; color:#828e77; }
  .browse-layer { display:flex; align-items:center; justify-content:space-between; gap:8px; width:100%; padding:11px 0 0; margin-top:7px; border:0; border-top:1px solid #c2ceb319; color:#d4dec8; font-size:11px; background:none; text-align:left; } .browse-layer:hover { color:white; }
  .feed-error,.limit-note,.empty-feed,.camera-note { font-size:11px; color:#c3b89e; line-height:1.6; } .feed-error button,.text-button { background:none; border:0; padding:0; color:#e0d9c6; text-decoration:underline; font-size:inherit; } .limit-note { color:#a4b197; } .empty-feed { color:#b7bfac; }
  .legend { display:flex; gap:4px; align-items:center; margin:12px 0; } .legend span { font-size:9px; color:#b1baa6; } .legend i { width:15px; height:3px; } .legend span:first-child { margin-right:3px; } .legend span:last-child { margin-left:3px; }
  footer { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:15px 20px; border-top:1px solid #ffffff17; background:#1c211bf5; flex-shrink:0; }
  .connection { display:flex; gap:7px; align-items:center; font-size:10px; color:#b7c1aa; } .connection i { width:4px; height:4px; border-radius:50%; background:#b8cba3; flex-shrink:0; } .connection.offline { color:#d8c39e; } .connection.offline i { background:#d8c39e; } footer button { border:0; background:none; padding:0; font-size:11px; text-decoration:underline; text-underline-offset:3px; color:#c5cdbb; } .coordinates { font-size:9px; letter-spacing:1px; color:#8b997f; }
  .activity-heading { display:flex; justify-content:space-between; gap:12px; padding:23px 10px 14px; color:#acb69f; font-size:10px; }
  .filter-chips { display:flex; flex-wrap:wrap; gap:6px; padding:0 10px 18px; } .filter-chips button { padding:7px 9px; background:none; border:1px solid #b6c4a528; border-radius:2px; font-size:11px; color:#b0bba4; } .filter-chips button.current { background:#bec9b0; border-color:#bec9b0; color:#232b1c; }
  .result-row { position:relative; display:grid; grid-template-columns:28px 1fr; gap:6px 9px; width:100%; padding:17px 25px 17px 10px; border:0; border-bottom:1px solid var(--edge); background:none; text-align:left; animation:row-in .5s calc(var(--row)*25ms) both; }
  .result-row:hover { background:#b9c6ac0a; } .result-row:hover .result-arrow { transform:translate(2px,-2px); } .result-row strong { grid-column:2; font-size:13px; font-weight:500; line-height:1.5; overflow-wrap:anywhere; } .result-row small { grid-column:2; font-size:11px; color:#a1ae93; line-height:1.5; } .result-symbol { grid-column:1; grid-row:1/4; color:#a7b79a; padding-top:3px; }
  .result-arrow { position:absolute; right:7px; top:22px; color:#aebc9f; transition:transform .3s; } .result-row time { grid-column:2; font-size:10px; color:#a7b799; }
  .load-more { display:flex; justify-content:space-between; width:calc(100% - 20px); margin:17px 10px; padding:13px; border:1px solid #b5c4a43b; border-radius:2px; color:#d4dfc8; background:#b7c7a709; font-size:12px; }
  .empty-state { padding:45px 18px; } .empty-state>:global(svg) { color:#a4b596; margin-bottom:25px; } .empty-state>span { display:block; font-size:24px; letter-spacing:-.6px; } .empty-state p { font-size:13px; color:#a5b297; line-height:1.8; margin:13px 0 24px; } .empty-state button { display:flex; align-items:center; justify-content:space-between; gap:30px; padding:12px; background:#c0cbb2; border:0; color:#252d1e; font-size:12px; }
  .skeleton-list { display:grid; gap:14px; padding:16px 10px; } .skeleton-list i { height:64px; background:linear-gradient(100deg,#ffffff03,#ffffff08,#ffffff03); background-size:200% 100%; animation:shimmer 1.6s infinite; }
  .map-tools { pointer-events:auto; position:absolute; right:24px; bottom:95px; display:flex; flex-direction:column; padding:4px; background:#171a19f5; border:1px solid var(--edge); border-radius:3px; }
  .map-tools button { display:grid; place-items:center; width:39px; height:39px; padding:0; background:none; border:0; color:#dbe2d1; font-size:22px; } .map-tools button:hover { background:#b8c5a614; } .map-tools>span { height:1px; margin:3px 6px; background:var(--edge); }
  .map-note { position:absolute; bottom:25px; right:24px; display:flex; flex-wrap:wrap; gap:6px 12px; font-size:9px; pointer-events:auto; color:#c1c8b8; padding:5px 8px; background:#171a19a8; } .map-note a { color:inherit; text-decoration:none; }
  .view-coordinates { position:absolute; left:24px; bottom:35px; display:flex; align-items:center; gap:12px; padding:11px 14px; border-left:1px solid #b7c6a74a; background:#171a19ed; color:#b9c5ac; font-size:10px; letter-spacing:.8px; font-variant-numeric:tabular-nums; } .crosshair { font-size:22px; font-weight:400; line-height:1; color:#e4e8dc; } .view-mode { padding-left:15px; border-left:1px solid #b7c6a72c; font-size:9px; }
  .map-tooltip { pointer-events:none; position:absolute; width:218px; padding:15px 17px; border:1px solid #b8c7aa40; background:#171a19fa; border-radius:3px; box-shadow:0 10px 30px #0004; animation:row-in .2s both; } .map-tooltip>span { display:block; text-transform:uppercase; letter-spacing:1px; font-size:9px; color:#aebda0; } .map-tooltip strong { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; font-size:14px; line-height:1.4; font-weight:500; margin:9px 0; } .map-tooltip small { font-size:10px; color:#99aa8b; }
  .mobile-trigger { display:none; }
  @keyframes interface-in { from { opacity:0; transform:translateY(16px); } to { opacity:1; transform:translateY(0); } }
  @keyframes title-in { from { opacity:0; transform:translateY(20px); clip-path:inset(0 0 100% 0); } to { opacity:1; transform:translateY(0); clip-path:inset(0); } }
  @keyframes row-in { from { opacity:0; transform:translateY(9px); } to { opacity:1; transform:translateY(0); } }
  @keyframes shimmer { to { background-position:-200% 0; } }
  @media(min-width:701px) and (max-width:1120px) { .city-time { display:none; } }
  @media(max-height:760px) and (min-width:701px) { .intro { padding:19px 25px; } .intro h1 { font-size:31px; margin:15px 0 10px; } .intro p { display:none; } .search-box { margin-top:12px; margin-bottom:10px; } .explorer { top:99px; bottom:79px; } }
  @media(max-height:560px) and (min-width:701px) { .intro { display:none; } .explorer { top:86px; bottom:65px; } .identity { top:14px; } .desktop-trigger { top:24px; } .city-time { top:28px; } .view-coordinates { bottom:16px; } }
  @media(max-width:700px) {
    .identity { top:17px; left:16px; padding:8px 10px; gap:8px; } .brand-mark { width:27px; height:30px; } .identity strong { font-size:18px; letter-spacing:-.7px; } .identity p { font-size:6px; letter-spacing:1px; } .city-time,.desktop-trigger,.intro,.view-coordinates,.map-note { display:none; }
    .explorer { top:auto; left:12px; bottom:91px; width:calc(100% - 24px); max-height:calc(100dvh - 190px); min-height:45dvh; background:#171a19fc; border-radius:8px; transform:translateY(35px); opacity:0; visibility:hidden; pointer-events:none; animation:none; transition:transform .55s cubic-bezier(.16,1,.3,1),opacity .25s,visibility .4s; }
    .explorer.mobile-open { opacity:1; transform:translateY(0); visibility:visible; pointer-events:auto; }
    .explorer::before { content:''; width:30px; height:3px; background:#b5c4a546; border-radius:3px; margin:10px auto 0; flex-shrink:0; } .search-box { margin:7px 22px 4px; padding:12px 0; } .search-box kbd { display:none; } .tabs { margin:0 20px; } .tabs button { padding:15px 0; }
    .panel-content { max-height:46dvh; padding-top:0; } .category-nav { margin-top:15px; } .layer-guidance { margin-bottom:16px; } .layer-row { padding:14px 10px; } footer { padding:13px 20px; }
    .category-nav button { min-height:44px; } .filter-chips button { min-height:40px; }
    .mobile-trigger { position:absolute; pointer-events:auto; display:flex; justify-content:space-between; align-items:center; left:16px; right:72px; bottom:31px; padding:17px 19px; border:1px solid #c3ceb450; border-radius:3px; background:#1a2118fa; color:#e4ebdb; font-size:13px; box-shadow:0 4px 24px #0003; }
    .mobile-trigger>span { font-size:11px; color:#afbd9e; } .map-tools { bottom:95px; right:16px; } .map-tools.mobile-covered { display:none; } .map-tools button { width:35px; height:36px; } .map-tooltip { display:none; }
  }
  @media(prefers-reduced-motion:reduce) { *,*::before,*::after { animation:none!important; transition:none!important; } }
</style>
