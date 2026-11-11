import { API_BASE_URL } from './liveLayers.js';
import { MAP_DATASETS, DATASET_BY_ID, EMPTY_COLLECTION, normalizeFeature, intersectsBounds, datasetParameters, isPrimaryEvent } from './explorerData.js';
import { createMapSymbolRegistry, markerKind, markerImageId, withMapSymbol } from './mapSymbols.js';
export { MAP_DATASETS } from './explorerData.js';

const LAYER_SUFFIXES = ['fill', 'line', 'point', 'cluster', 'count'];
const CACHE_TTL = 45000;
const MAX_REQUESTS = 2;

export function createMapDataController(map, onChange, onSelect, onHover = () => {}, { decodeSymbol } = {}) {
  const entries = new Map();
  const cache = new Map();
  const queue = new Set();
  const animationTimers = new Set();
  let disposed = false;
  let installing = false;
  let installQueued = false;
  let viewportTimer;
  let hoverFrame;
  let hoverEvent;
  let running = 0;
  let selection = null;
  const symbols = createMapSymbolRegistry(map, styleChanged, decodeSymbol);
  const bounds = () => {
    const b = map.getBounds();
    return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
  };
  function visibleFeatures(entry) {
    return (entry.data?.features || []).filter(feature => intersectsBounds(feature, bounds()));
  }
  function notify() {
    if (disposed) return;
    onChange(Object.fromEntries([...entries].map(([id, entry]) => [id, {
      enabled: true, status: entry.status, features: visibleFeatures(entry),
      updatedAt: entry.updatedAt, filters: { ...entry.filters }, truncated: entry.truncated,
      error: entry.error, totalLoaded: entry.data?.features.length || 0
    }])));
  }
  function detach(id) {
    if (!map.getStyle()) return;
    for (const suffix of LAYER_SUFFIXES) {
      const layer = `explore-${id}-${suffix}`;
      if (map.getLayer(layer)) map.removeLayer(layer);
    }
    if (map.getSource(`explore-${id}`)) map.removeSource(`explore-${id}`);
  }
  function addLayer(layer) {
    // Data markers and their labels remain legible above the visual cloud canopy.
    if (map.getLayer(layer.id)) return;
    const opacity = ['icon-opacity', 'line-opacity', 'fill-opacity', 'text-opacity'].find(key => layer.paint?.[key] != null);
    if (!opacity || reducedMotion()) { map.addLayer(layer); return; }
    const target = layer.paint[opacity];
    map.addLayer({ ...layer, paint: { ...layer.paint, [opacity]: 0, [`${opacity}-transition`]: { duration: 220 } } });
    const timer = setTimeout(() => {
      animationTimers.delete(timer);
      if (!disposed && map.getLayer(layer.id)) map.setPaintProperty(layer.id, opacity, target);
    }, 20);
    animationTimers.add(timer);
  }
  function installSelection() {
    if (!selection) return;
    if (selection.geometry.type === 'Point' && !symbols.ensure(markerKind(selection), true)) return;
    const source = 'explorer-selection';
    if (map.getSource(source)) map.getSource(source).setData({ type: 'FeatureCollection', features: [selection] });
    else {
      map.addSource(source, { type: 'geojson', data: { type: 'FeatureCollection', features: [selection] } });
      addLayer({ id: `${source}-area`, type: 'line', source, filter: ['!=', ['geometry-type'], 'Point'], paint: { 'line-color': '#e7e6da', 'line-width': 3, 'line-opacity': 0.9 } });
      addLayer({ id: `${source}-point`, type: 'symbol', source, filter: ['==', ['geometry-type'], 'Point'], layout: { 'icon-image': ['get', '__selectedMarker'], 'icon-size': 1.02, 'icon-anchor': 'bottom', 'icon-offset': [0, 4], 'icon-allow-overlap': true, 'icon-ignore-placement': true }, paint: { 'icon-opacity': 1 } });
    }
  }
  function install() {
    if (disposed || installing || !map.getStyle()) return;
    installing = true;
    try {
      for (const [id, entry] of entries) {
        if (!entry.data) continue;
        const source = `explore-${id}`;
        const definition = DATASET_BY_ID[id];
        const points = !definition.geometry;
        const clusterKind = `cluster-${markerKind({ properties: { __dataset: id, ...entry.filters } })}`;
        const kinds = new Set(entry.data.features.filter(feature => feature.geometry.type === 'Point').map(markerKind));
        const imagesReady = [...kinds].map(kind => symbols.ensure(kind)).every(Boolean);
        const clusterReady = !points || !entry.data.features.length || symbols.ensure(clusterKind);
        if (!imagesReady || !clusterReady) continue;
        let mapSource = map.getSource(source);
        if (!mapSource) {
          map.addSource(source, { type: 'geojson', data: entry.data, ...(points ? { cluster: true, clusterRadius: 42, clusterMaxZoom: 13 } : {}) });
          mapSource = map.getSource(source);
        } else if (entry.installedSource !== mapSource || entry.installedData !== entry.data) mapSource.setData(entry.data);
        entry.installedSource = mapSource; entry.installedData = entry.data;
        const color = definition.color;
        const thematicColor = id === 'crowd'
          ? ['interpolate', ['linear'], ['coalesce', ['get', 'crowd_index'], 0], 0, '#9dac8c', 40, '#c2b18d', 70, '#b18e79', 100, '#a77670']
          : id === 'traffic'
            ? ['match', ['get', 'congestion_level'], 'free_flow', '#9dac8c', 'moderate', '#c2b18d', 'heavy', '#b18e79', 'standstill', '#a77670', color]
            : color;
        addLayer({ id: `${source}-fill`, type: 'fill', source, filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': thematicColor, 'fill-opacity': id === 'crowd' ? 0.32 : 0.10, 'fill-opacity-transition': { duration: 250 } } });
        addLayer({ id: `${source}-line`, type: 'line', source, filter: ['!=', ['geometry-type'], 'Point'], layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': thematicColor, 'line-width': id === 'traffic' ? 4 : 1.1, 'line-opacity': 0.85 } });
        addLayer({ id: `${source}-point`, type: 'symbol', source, filter: ['all', ['==', ['geometry-type'], 'Point'], ['!', ['has', 'point_count']]], layout: { 'icon-image': ['get', '__marker'], 'icon-size': ['interpolate', ['linear'], ['zoom'], 10, 0.8, 16, 0.9], 'icon-anchor': 'bottom', 'icon-offset': [0, 4], 'icon-padding': 5, 'symbol-z-order': 'viewport-y' }, paint: { 'icon-opacity': 1, 'icon-opacity-transition': { duration: 250 } } });
        if (points) {
          if (map.getLayer(`${source}-cluster`) && entry.installedClusterKind !== clusterKind) map.setLayoutProperty(`${source}-cluster`, 'icon-image', markerImageId(clusterKind));
          addLayer({ id: `${source}-cluster`, type: 'symbol', source, filter: ['has', 'point_count'], layout: { 'icon-image': markerImageId(clusterKind), 'icon-size': ['step', ['get', 'point_count'], 0.9, 10, 0.95, 50, 1.08], 'icon-allow-overlap': true, 'icon-ignore-placement': true }, paint: { 'icon-opacity': 1 } });
          addLayer({ id: `${source}-count`, type: 'symbol', source, filter: ['has', 'point_count'], layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 11, 'text-font': ['Noto Sans Regular'], 'text-offset': [1, -0.1], 'text-allow-overlap': true, 'text-ignore-placement': true }, paint: { 'text-color': '#263025', 'text-opacity': 1 } });
          entry.installedClusterKind = clusterKind;
        }
      }
      installSelection();
    } catch (_) {
      // MapLibre can emit styledata before a replacement style accepts sources.
      // Keep accepted data and retry installation on its next style event.
    } finally { installing = false; }
  }
  function styleChanged() {
    if (disposed || installQueued) return;
    installQueued = true;
    // MapLibre emits styledata after evaluating layers, inside its render pass.
    // Defer new symbol layers so their layout is evaluated before placement.
    queueMicrotask(() => { installQueued = false; install(); });
  }
  async function request(id, entry, revision) {
    const abort = new AbortController();
    entry.abort = abort;
    entry.status = 'loading';
    entry.error = null;
    notify();
    const definition = DATASET_BY_ID[id];
    const params = datasetParameters(definition, entry.filters, bounds());
    const key = `${id}?${params}`;
    const timeout = setTimeout(() => abort.abort(), 15000);
    try {
      let snapshot = cache.get(key);
      if (!snapshot || Date.now() - snapshot.time > CACHE_TTL) {
        const response = await fetch(`${API_BASE_URL}/api/v1${definition.path}?${params}`, { signal: abort.signal });
        if (!response.ok) throw new Error(response.status === 429 ? 'Too many requests. We’ll try again shortly.' : 'This feed is temporarily unavailable.');
        const data = await response.json();
        if (data.type !== 'FeatureCollection' || !Array.isArray(data.features)) throw new Error('The feed returned an unexpected response.');
        const time = Date.now();
        const features = data.features.filter(feature => feature?.type === 'Feature' && feature.geometry && feature.properties && intersectsBounds(feature, [-180, -90, 180, 90])).map(feature => withMapSymbol(normalizeFeature(feature, id, time))).filter(feature => id !== 'events' || isPrimaryEvent(feature));
        snapshot = { time, data: { type: 'FeatureCollection', features }, truncated: !definition.citywide && data.features.length >= 150 };
        cache.set(key, snapshot);
        if (cache.size > 32) cache.delete(cache.keys().next().value);
      }
      if (entries.get(id) !== entry || entry.revision !== revision || abort.signal.aborted || disposed) return;
      entry.data = snapshot.data;
      entry.status = 'ready';
      entry.updatedAt = snapshot.time;
      entry.truncated = snapshot.truncated;
      install();
    } catch (error) {
      if (entries.get(id) === entry && entry.revision === revision && entry.abort === abort && !disposed) {
        entry.status = entry.data ? 'stale' : 'error';
        entry.error = error.name === 'AbortError' ? 'The feed took too long to respond.' : error.message;
      }
    } finally { clearTimeout(timeout); if (entry.abort === abort) entry.abort = null; notify(); }
  }
  function pump() {
    if (disposed) return;
    while (running < MAX_REQUESTS && queue.size) {
      const id = queue.values().next().value;
      queue.delete(id);
      const entry = entries.get(id);
      if (!entry) continue;
      running++;
      request(id, entry, entry.revision).finally(() => { running--; pump(); });
    }
  }
  function enqueue(id) {
    const entry = entries.get(id);
    if (!entry || disposed) return;
    // A superseded response cannot overwrite the next viewport/filter selection.
    entry.abort?.abort();
    entry.revision = (entry.revision || 0) + 1;
    entry.status = 'loading';
    queue.add(id); notify(); pump();
  }
  function toggle(id) {
    if (!DATASET_BY_ID[id] || disposed) return;
    leave();
    if (entries.has(id)) {
      entries.get(id).abort?.abort(); entries.delete(id); queue.delete(id); detach(id);
      if (selection?.properties.__dataset === id) select(null);
      notify();
    } else {
      entries.set(id, { status: 'loading', filters: { ...DATASET_BY_ID[id].defaults } });
      enqueue(id);
    }
  }
  function setFilters(id, patch) {
    const entry = entries.get(id);
    if (!entry) return;
    leave();
    for (const filter of DATASET_BY_ID[id].filters || []) {
      if (filter.options.some(([key]) => key === patch[filter.key])) entry.filters[filter.key] = patch[filter.key];
    }
    entry.abort?.abort(); entry.data = null; entry.updatedAt = null;
    map.getSource(`explore-${id}`)?.setData(EMPTY_COLLECTION);
    if (selection?.properties.__dataset === id) select(null);
    enqueue(id);
  }
  function select(feature) {
    leave();
    selection = feature ? withMapSymbol(normalizeFeature(feature)) : null;
    if (!selection) {
      map.getSource('explorer-selection')?.setData(EMPTY_COLLECTION);
    } else install();
    onSelect(selection);
  }
  function viewportChanged() {
    notify(); clearTimeout(viewportTimer);
    viewportTimer = setTimeout(() => entries.forEach((_, id) => enqueue(id)), 400);
  }
  function hitLayers() {
    return [...entries.keys()].flatMap(id => LAYER_SUFFIXES.map(s => `explore-${id}-${s}`)).filter(id => map.getLayer(id));
  }
  function click(event) {
    const layers = hitLayers();
    if (!layers.length) return;
    const hits = map.queryRenderedFeatures(event.point, { layers });
    const hit = hits.find(f => f.geometry.type === 'Point') || hits[0];
    if (!hit) return;
    if (hit.properties.cluster) {
      const source = map.getSource(hit.source);
      source?.getClusterExpansionZoom(hit.properties.cluster_id, (error, zoom) => {
        if (!error && !disposed && map.getSource(hit.source) === source) map.easeTo({ center: hit.geometry.coordinates, zoom, duration: reducedMotion() ? 0 : 500 });
      });
    } else select(hit);
  }
  function reducedMotion() { return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches; }
  function hover(event) {
    hoverEvent = event;
    if (hoverFrame || typeof requestAnimationFrame === 'undefined') return;
    hoverFrame = requestAnimationFrame(() => {
      hoverFrame = null;
      if (disposed) return;
      const layers = hitLayers();
      const point = hoverEvent.point;
      const hits = layers.length ? map.queryRenderedFeatures(point, { layers }) : [];
      const hit = hits.find(feature => feature.geometry.type === 'Point') || hits[0];
      map.getCanvas().style.cursor = hit ? 'pointer' : '';
      onHover(hit && !hit.properties.cluster ? { feature: normalizeFeature(hit), point: { x: point.x, y: point.y } } : null);
    });
  }
  function leave() {
    if (hoverFrame) cancelAnimationFrame(hoverFrame);
    hoverFrame = null; hoverEvent = null;
    if (map.getCanvas) map.getCanvas().style.cursor = '';
    onHover(null);
  }
  function refresh() { entries.forEach((_, id) => enqueue(id)); }
  function visibility() { if (document.visibilityState === 'visible') refresh(); }
  const poll = setInterval(() => { if (typeof document === 'undefined' || document.visibilityState !== 'hidden') refresh(); }, 60000);
  map.on('moveend', viewportChanged);
  map.on('styledata', styleChanged);
  map.on('click', click);
  map.on('mousemove', hover);
  map.on('mouseout', leave);
  map.on('movestart', leave);
  if (typeof document !== 'undefined') document.addEventListener('visibilitychange', visibility);
  return { toggle, setFilters, select, retry: enqueue, refresh, clear: () => [...entries.keys()].forEach(toggle), destroy() {
    disposed = true; clearTimeout(viewportTimer); clearInterval(poll); queue.clear();
    animationTimers.forEach(clearTimeout); animationTimers.clear();
    leave();
    entries.forEach(e => e.abort?.abort());
    map.off('moveend', viewportChanged); map.off('styledata', styleChanged); map.off('click', click); map.off('mousemove', hover);
    map.off('mouseout', leave); map.off('movestart', leave);
    if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', visibility);
    if (map.getStyle()) {
      [...entries.keys()].forEach(detach);
      for (const id of ['explorer-selection-point', 'explorer-selection-area']) if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource('explorer-selection')) map.removeSource('explorer-selection');
    }
    symbols.destroy();
    entries.clear(); cache.clear();
  } };
}
