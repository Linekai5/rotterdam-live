<script>
  import { onDestroy } from 'svelte';
  import { fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { API_BASE_URL } from './liveLayers.js';
  import { DATASET_BY_ID, featureTitle, featureSubtitle, featureDetails, featureDescription, featureAction, safeLink, formatNumber, formatDate } from './explorerData.js';
  import ExplorerIcon from './ExplorerIcon.svelte';
  import { language, t } from './i18n.js';
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
  $: rows = featureDetails(feature, $language);
  $: action = featureAction(feature);
  $: description = featureDescription(feature, $language);
  $: highlight = primaryMetric(properties, $language, $t);

  function primaryMetric(p, language, translate) {
    const details = p.details || {};
    const number = value => formatNumber(value, language);
    if (p.__dataset === 'parking' && Number.isFinite(details.available_spaces)) {
      const unit = Number.isFinite(details.total_capacity)
        ? translate('of {count} spaces', { count: number(details.total_capacity) }) : translate('spaces');
      return { label: translate('Spaces available'), value: number(details.available_spaces), unit, number: true };
    }
    if (p.__dataset === 'traffic' && Number.isFinite(p.speed_kmh)) {
      return { label: translate('Current corridor speed'), value: number(p.speed_kmh), unit: 'km/h', number: true };
    }
    if (p.__dataset === 'crowd' && Number.isFinite(p.crowd_index)) {
      return { label: translate('Estimated district activity'), value: number(p.crowd_index), unit: translate('/ 100 · model estimate'), number: true };
    }
    if (p.__dataset === 'bridges' && typeof details.active_opening === 'boolean') {
      return { label: translate('Opening for vessels'), value: translate(details.active_opening ? 'In progress' : 'Not active'), unit: translate('Latest reported status') };
    }
    if (p.__dataset === 'events' && p.start_time) {
      return { label: translate('Next on the calendar'), value: formatDate(p.start_time, true, language), unit: p.venue?.name || p.venue_name || 'Rotterdam' };
    }
    if (p.__dataset === 'environment' && Number.isFinite(details.pm25)) {
      return { label: translate('Fine particulate matter'), value: number(details.pm25), unit: 'µg/m³ · PM2.5', number: true };
    }
    return null;
  }
  $: candidateDistrict = properties.district_name || properties.district || (properties.__dataset === 'districts' ? properties.name : null);
  $: district = ['Rotterdam', 'Rotterdam-Rijnmond'].includes(candidateDistrict) ? null : candidateDistrict;
  $: if (previousFeature !== feature) {
    previousFeature = feature; profileAbort?.abort(); profileAbort = null; profile = null; profileStatus = 'idle'; imageFailed = false;
  }
  onDestroy(() => { profileAbort?.abort(); profileAbort = null; });
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

<section class="selection-card" class:full-map={!explorerOpen} aria-label={$t('Location details')} in:fly={{ x: 18, duration: reducedMotion ? 0 : 420, easing: cubicOut }} out:fly={{ x: 10, duration: reducedMotion ? 0 : 160 }}>
  <div class="card-heading">
    <span class="category-mark"><ExplorerIcon name={dataset?.icon || 'pin'} size={19}/></span>
    <span class="eyebrow">{$t(dataset?.label || 'A PLACE IN ROTTERDAM')}</span>
    <button class="close" aria-label={$t('Close location details')} on:click={onClose}><ExplorerIcon name="close" size={17}/></button>
  </div>
  {#key feature?.id || properties.id || featureTitle(feature)}
    <div class="record-body" in:fly={{ y: 10, duration: reducedMotion ? 0 : 320, easing: cubicOut }}>
      {#if !imageFailed && safeLink(properties.image_url)}<div class="image-frame"><img class="event-image" src={safeLink(properties.image_url)} alt="" loading="lazy" on:error={() => imageFailed = true}/></div>{/if}
      <div class="content">
        <span class="place-label">{$t('SELECTED LOCATION')} <span aria-hidden="true">↗</span></span>
        <h2>{featureTitle(feature, $language)}</h2>
        <p class="subtitle">{featureSubtitle(feature, $language)}</p>
        {#if layerState?.status === 'stale'}<div class="record-state" role="status">{$t('Last available record · this feed could not refresh.')}</div>{/if}
        {#if highlight}
          <div class="primary-metric" class:numeric={highlight.number}>
            <span class="metric-label">{highlight.label}</span>
            <div><strong>{highlight.value}</strong><span>{highlight.unit}</span></div>
            <svg class="metric-rule" viewBox="0 0 280 8" preserveAspectRatio="none" aria-hidden="true"><path d="M0 7h267l7-6h6"/></svg>
          </div>
        {/if}
        {#if description}<p class="description">{description}</p>{/if}
        {#if rows.length}<dl>{#each rows as row, index}<div style={`--row:${Math.min(index, 8)}`}><dt>{row.label}</dt><dd>{row.value}</dd></div>{/each}</dl>{/if}
        {#if profileStatus === 'ready'}
          <div class="profile" role="region" aria-label={$t('District profile')} in:fly={{ y: 8, duration: reducedMotion ? 0 : 260 }}>
            <span class="eyebrow">{profile.demographics?.data_year || ''} {$t('DISTRICT PROFILE')}</span>
            <h3>{profile.district_name}</h3>
            <div class="profile-grid"><div><strong>{formatNumber(profile.demographics?.total_population, $language)}</strong><span>{$t('Residents')}</span></div><div><strong>{formatNumber(profile.housing?.surface_area?.average_m2, $language)}<small> m²</small></strong><span>{$t('Average home')}</span></div></div>
            <p>{profile.demographics?.source || $t('District statistics')} · {$t('Annual statistics, not live readings.')}</p>
          </div>
        {/if}
        {#if profileStatus === 'error'}<p class="record-state" role="status">{$t('The district profile is unavailable right now.')}</p>{/if}
        <div class="actions">
          {#if action}<a class="primary-action" href={action.href} target="_blank" rel="noopener noreferrer">{$t(action.label)}<ExplorerIcon name="arrow" size={16}/></a>{/if}
          {#if district && profileStatus !== 'ready'}<button disabled={profileStatus === 'loading'} on:click={loadProfile}>{$t(profileStatus === 'loading' ? 'Loading district profile…' : profileStatus === 'error' ? 'Retry district profile' : 'Explore this district')}<ExplorerIcon name="district" size={16}/></button>{/if}
          {#if canFocus}<button on:click={onFocus}>{$t('Show on map')}<ExplorerIcon name="pin" size={16}/></button>{:else}<p class="record-state">{$t('This place is outside the central map area. Its location details are shown here.')}</p>{/if}
        </div>
      </div>
    </div>
  {/key}
</section>

<style>
  .selection-card {
    position:absolute; pointer-events:auto; left:calc(var(--explorer-inset, 24px) + var(--explorer-width, 352px) + 16px); bottom:28px;
    width:360px; max-width:calc(100vw - 32px); max-height:calc(100dvh - 114px); overflow:auto; box-sizing:border-box;
    color:#f0eee7; background:#171a19fa; border:1px solid #d5dfce29; border-radius:4px 18px 4px 4px;
    box-shadow:0 20px 60px #0003; scrollbar-width:thin; scrollbar-color:#4d5648 transparent; font-family:inherit; font-size:13px; line-height:1.5;
  }
  .card-heading { display:flex; align-items:center; gap:11px; min-height:57px; padding:0 22px; border-bottom:1px solid #ffffff14; }
  .category-mark { display:grid; place-items:center; color:#b9c5ac; }
  .eyebrow { font-size:10px; line-height:1.5; letter-spacing:1.25px; text-transform:uppercase; color:#b9c5ac; }
  .close { display:grid; place-items:center; margin-left:auto; width:44px; height:44px; padding:0; border:1px solid transparent; border-radius:50%; color:#b7bcb3; background:transparent; cursor:pointer; transition:transform .25s,background .25s,border-color .25s; }
  .close:hover { transform:rotate(90deg); border-color:#ffffff24; background:#ffffff06; }
  .content { padding:25px 24px 23px; }
  .image-frame { overflow:hidden; border-bottom:1px solid #ffffff16; }
  .event-image { display:block; width:100%; height:165px; object-fit:cover; filter:saturate(.45) brightness(.8); animation:image-settle 800ms cubic-bezier(.2,.7,.2,1) both; }
  .place-label { display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; font-size:9px; letter-spacing:1.6px; color:#929b8e; }
  .place-label span { font-size:17px; letter-spacing:0; color:#b9c5ac; }
  h2 { font-size:27px; font-weight:500; line-height:1.14; letter-spacing:-1px; margin:0 0 12px; overflow-wrap:anywhere; text-wrap:balance; }
  .subtitle { margin:0; color:#a8b0a2; font-size:12px; line-height:1.6; }
  .primary-metric { position:relative; padding:22px 0 20px; margin-top:20px; border-top:1px solid #ffffff18; }
  .metric-label { display:block; font-size:10px; letter-spacing:.4px; color:#a8b0a2; }
  .primary-metric>div { display:flex; flex-wrap:wrap; align-items:baseline; gap:9px; margin-top:9px; }
  .primary-metric strong { font-size:25px; font-weight:450; line-height:1.18; letter-spacing:-1px; }
  .primary-metric.numeric strong { font-size:53px; letter-spacing:-3px; font-variant-numeric:tabular-nums; }
  .primary-metric>div>span { color:#a8b0a2; font-size:11px; }
  .metric-rule { position:absolute; bottom:0; left:0; width:100%; height:8px; fill:none; stroke:#b9c5ac66; stroke-width:1; }
  .metric-rule path { stroke-dasharray:290; stroke-dashoffset:290; animation:trace-rule 650ms 100ms cubic-bezier(.2,.7,.2,1) forwards; }
  .description { font-size:12px; color:#b0b6ab; line-height:1.8; max-height:170px; overflow:auto; margin:21px 0; }
  .record-state { padding:11px 12px; border-left:2px solid #bcae90; background:#bcae9009; color:#c8bda7; font-size:11px; line-height:1.6; margin:17px 0 0; }
  dl { margin:23px 0 0; }
  dl>div { display:grid; grid-template-columns:minmax(90px, .85fr) 1.4fr; gap:16px; padding:11px 0; border-bottom:1px solid #ffffff10; font-size:12px; line-height:1.5; animation:record-reveal 350ms calc(var(--row) * 28ms) both; }
  dt { color:#949e8e; }
  dd { margin:0; color:#d9ddd3; text-align:right; overflow-wrap:anywhere; }
  .actions { display:grid; gap:7px; margin-top:24px; }
  .actions a,.actions button { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:13px 14px; font:inherit; font-size:12px; border:1px solid #ffffff20; border-radius:3px; color:#e1e4da; background:transparent; text-decoration:none; cursor:pointer; text-align:left; transition:background .2s,border-color .2s; }
  .actions .primary-action { background:#b9c5ac; color:#1c211a; border-color:#b9c5ac; }
  .actions a:hover,.actions button:hover { background:#ffffff09; border-color:#b9c5ac88; }
  .actions .primary-action:hover { background:#cbd4c1; border-color:#cbd4c1; }
  .actions :global(svg) { flex-shrink:0; transition:transform .25s cubic-bezier(.2,.7,.2,1); }
  .actions a:hover :global(svg),.actions button:hover :global(svg) { transform:translate(2px,-2px); }
  .actions button:disabled { opacity:.55; cursor:wait; }
  button:focus-visible,a:focus-visible { outline:2px solid #d9e2ce; outline-offset:3px; }
  .profile { margin-top:24px; border-top:1px solid #b9c5ac55; padding-top:21px; }
  h3 { font-size:23px; font-weight:450; line-height:1.2; letter-spacing:-.6px; margin:11px 0 21px; }
  .profile-grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
  .profile-grid>div+div { padding-left:20px; border-left:1px solid #ffffff1b; }
  .profile-grid strong { display:block; font-weight:450; font-size:27px; line-height:1; letter-spacing:-1px; }
  .profile-grid span { display:block; font-size:11px; color:#a1ad96; margin-top:8px; }
  .profile-grid small { font-size:13px; }
  .profile p { font-size:10px; color:#969f8f; line-height:1.7; margin:19px 0 0; }
  .selection-card.full-map { left:24px; }
  @keyframes image-settle { from { transform:scale(1.045); } to { transform:scale(1); } }
  @keyframes trace-rule { to { stroke-dashoffset:0; } }
  @keyframes record-reveal { from { opacity:0; transform:translateY(5px); } to { opacity:1; transform:translateY(0); } }
  @media(max-width:1050px) and (min-width:701px) { .selection-card { width:calc(100vw - var(--explorer-width, 352px) - 64px); min-width:260px; max-width:360px; } }
  @media(max-width:700px) { .selection-card,.selection-card.full-map { left:12px; bottom:84px; width:calc(100% - 24px); max-height:calc(100dvh - 220px); border-radius:18px 18px 4px 4px; z-index:5; } .content { padding:22px; } .card-heading { min-height:52px; } .event-image { height:125px; } h2 { font-size:26px; } }
  @media(prefers-reduced-motion:reduce) { *,*::before,*::after { animation:none!important; transition:none!important; } .metric-rule path { stroke-dashoffset:0; } }
</style>
