<script>
  import { onDestroy } from 'svelte';
  import { fly } from 'svelte/transition';
  import { API_BASE_URL } from './liveLayers.js';
  import { DATASET_BY_ID, featureTitle, featureSubtitle, featureDetails, featureDescription, featureAction, safeLink, formatNumber } from './explorerData.js';
  import ExplorerIcon from './ExplorerIcon.svelte';
  export let feature;
  export let layerState = null;
  export let canFocus = true;
  export let explorerOpen = true;
  export let reducedMotion = false;
  export let onClose = () => {};
  export let onFocus = () => {};
  let profile = null;
  let profileStatus = 'idle';
  let profileAbort;
  let imageFailed = false;
  let previousFeature;
  $: properties = feature?.properties || {};
  $: dataset = DATASET_BY_ID[properties.__dataset];
  $: rows = featureDetails(feature);
  $: action = featureAction(feature);
  $: candidateDistrict = properties.district_name || properties.district || (properties.__dataset === 'districts' ? properties.name : null);
  $: district = ['Rotterdam', 'Rotterdam-Rijnmond'].includes(candidateDistrict) ? null : candidateDistrict;
  $: if (previousFeature !== feature) {
    previousFeature = feature; profileAbort?.abort(); profile = null; profileStatus = 'idle'; imageFailed = false;
  }
  onDestroy(() => profileAbort?.abort());
  async function loadProfile() {
    profileAbort?.abort();
    const abort = new AbortController(); profileAbort = abort; profileStatus = 'loading';
    const timer = setTimeout(() => abort.abort(), 12000);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/living/districts/${encodeURIComponent(district)}/passport`, { signal: abort.signal });
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (data.type !== 'Feature' || !data.properties) throw new Error();
      if (profileAbort === abort) { profile = data.properties; profileStatus = 'ready'; }
    } catch (_) { if (profileAbort === abort) profileStatus = 'error'; }
    finally { clearTimeout(timer); }
  }
</script>

<section class="selection-card" class:full-map={!explorerOpen} aria-label="Location details" in:fly={{ y: 14, duration: reducedMotion ? 0 : 280 }} out:fly={{ y: 8, duration: reducedMotion ? 0 : 140 }}>
  <div class="card-heading"><span class="eyebrow">{dataset?.label || 'A PLACE IN ROTTERDAM'}</span><button class="close" aria-label="Close location details" on:click={onClose}><ExplorerIcon name="close" size={17}/></button></div>
  {#if !imageFailed && safeLink(properties.image_url)}<img class="event-image" src={safeLink(properties.image_url)} alt="" loading="lazy" on:error={() => imageFailed = true}/>{/if}
  <div class="content">
    <h2>{featureTitle(feature)}</h2><p class="subtitle">{featureSubtitle(feature)}</p>
    {#if layerState?.status === 'stale'}<div class="record-state">Last available record · this feed could not refresh.</div>{/if}
    {#if featureDescription(feature)}<p class="description">{featureDescription(feature)}</p>{/if}
    {#if rows.length}<dl>{#each rows as row}<div><dt>{row.label}</dt><dd>{row.value}</dd></div>{/each}</dl>{/if}
    {#if profileStatus === 'ready'}
      <div class="profile" role="region" aria-label="District profile"><span class="eyebrow">{profile.demographics?.data_year || ''} DISTRICT PROFILE</span><h3>{profile.district_name}</h3><div class="profile-grid"><div><strong>{formatNumber(profile.demographics?.total_population)}</strong><span>Residents</span></div><div><strong>{formatNumber(profile.housing?.surface_area?.average_m2)}<small> m²</small></strong><span>Average home</span></div></div><p>{profile.demographics?.source || 'District statistics'} · Annual statistics, not live readings.</p></div>
    {/if}
    {#if profileStatus === 'error'}<p class="record-state" role="status">The district profile is unavailable right now.</p>{/if}
    <div class="actions">
      {#if action}<a href={action.href} target="_blank" rel="noopener noreferrer">{action.label}<ExplorerIcon name="arrow" size={13}/></a>{/if}
      {#if district && profileStatus !== 'ready'}<button disabled={profileStatus === 'loading'} on:click={loadProfile}>{profileStatus === 'loading' ? 'Loading district profile…' : profileStatus === 'error' ? 'Retry district profile' : 'Explore this district'}<ExplorerIcon name="district" size={14}/></button>{/if}
      {#if canFocus}<button on:click={onFocus}>Show on map<ExplorerIcon name="pin" size={14}/></button>{:else}<p class="record-state">This place is outside the central map area. Its location details are shown here.</p>{/if}
    </div>
  </div>
</section>

<style>
  .selection-card{position:absolute;pointer-events:auto;left:380px;bottom:28px;width:340px;max-width:calc(100vw - 32px);max-height:calc(100dvh - 100px);overflow:auto;background:#1d231ff7;color:#e3e6da;border:1px solid #ffffff1c;border-radius:14px;box-shadow:0 16px 70px #0005;scrollbar-width:thin;scrollbar-color:#46523c transparent;box-sizing:border-box}.card-heading{display:flex;align-items:center;justify-content:space-between;padding:16px 22px;border-bottom:1px solid #ffffff0c}.eyebrow{font-size:9px;letter-spacing:1.5px;text-transform:uppercase;color:#aebb9e}.close{display:grid;place-items:center;width:28px;height:28px;padding:0;border:0;border-radius:5px;background:#ffffff04;color:#bac5b1;cursor:pointer}.content{padding:22px}.event-image{display:block;width:100%;height:145px;object-fit:cover;filter:saturate(.28) brightness(.8);border-bottom:1px solid #ffffff15}h2{font:27px/1.18 Georgia,serif;letter-spacing:-.5px;margin:0 0 12px;overflow-wrap:anywhere}.subtitle{font-size:11px;color:#b5c0a9;line-height:1.6;margin:0}.description{font-size:12px;color:#a6b09e;line-height:1.85;max-height:150px;overflow:auto;margin:18px 0 20px}.record-state{padding:10px 12px;border:1px solid #bdad8b33;background:#bdad8b08;border-radius:6px;color:#c4b89f;font-size:10px;line-height:1.6;margin-top:14px}dl{margin:21px 0 0}dl>div{display:grid;grid-template-columns:100px 1fr;gap:15px;padding:10px 0;border-top:1px solid #ffffff10;font-size:10px;line-height:1.6}dt{color:#94a289}dd{margin:0;color:#d3dacc;text-align:right;overflow-wrap:anywhere}.actions{display:grid;gap:8px;margin-top:20px}.actions a,.actions button{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 12px;font:11px system-ui,sans-serif;border:1px solid #b1bfa433;background:#b1bfa407;border-radius:7px;color:#d9dfd1;text-decoration:none;cursor:pointer;text-align:left;transition:background .2s}.actions a:hover,.actions button:hover{background:#b1bfa416}.actions button:disabled{opacity:.5;cursor:wait}button:focus-visible,a:focus-visible{outline:2px solid #c2ccb8;outline-offset:-3px}.profile{border:1px solid #ffffff13;background:#ffffff03;border-radius:8px;padding:16px;margin-top:20px}h3{font:20px Georgia,serif;margin:10px 0 16px}.profile-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.profile-grid strong{display:block;font-weight:450;font-size:23px;letter-spacing:-.5px}.profile-grid span{display:block;font-size:9px;color:#9eae91;margin-top:6px}.profile-grid small{font-size:12px}.profile p{font-size:9px;color:#91a083;line-height:1.7;margin:18px 0 0}@media(max-width:1000px) and (min-width:701px){.selection-card{left:370px;width:calc(100vw - 390px);max-width:340px}}@media(max-width:700px){.selection-card{left:12px;bottom:82px;width:calc(100% - 24px);max-height:calc(100dvh - 230px);z-index:5}.content{padding:20px}.event-image{height:110px}h2{font-size:25px}}@media(prefers-reduced-motion:reduce){*{transition:none!important}}
@media(min-width:701px){.selection-card.full-map{left:24px}}
</style>
