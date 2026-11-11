// Original 24-unit line drawings shared by the interface and the map sprite.
// All drawings are local SVG; no icon font or remote sprite is requested.
export const ICON_PATHS = {
  event: 'M4 5h16v5a2 2 0 0 0 0 4v5H4v-5a2 2 0 0 0 0-4V5Zm11 0v3m0 3v2m0 3v3M8 9v6m3-6v6',
  concert: 'M9 17V5l11-2v12M9 8l11-2M9 17c0 2-3 4-5 3s-1-4 2-4h3Zm11-2c0 2-3 4-5 3s-1-4 2-4h3Z',
  festival: 'M5 21V3m0 1 14 3-5 4 5 4-14-3M2 21h6m11-2v3m-2-1h4',
  theatre: 'm2 4 9 2v7c0 3-3 5-5 5-3-2-4-4-4-7V4Zm3 5h1m2 0h1m-4 4c1-1 2-1 3 0m5-8 9-1v7c0 5-2 8-5 10-3-2-5-5-5-9m3-3h1m2-1h1m-4 7c1 2 3 2 4 0',
  exhibition: 'M3 4h18v16H3V4Zm4 12 4-5 3 3 3-4 3 6M7 8h.01M7 20v2m10-2v2',
  football: 'm12 2 7 4 3 8-5 7H7l-5-7 3-8 7-4Zm0 6-4 3 2 5h5l2-5-5-3Zm0-6v6m7-2-2 5m5 3-7 2m2 5-2-5M7 21l3-5m-8-2 6-3M5 6l3 5',
  district: 'm3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2V5Zm6-2v16m6-14v16',
  shop: 'M4 11v9h16v-9M3 10l2-6h14l2 6M3 10c1 2 3 2 4 0 1 2 3 2 5 0 2 2 4 2 5 0 1 2 3 2 4 0M9 20v-6h6v6',
  bakery: 'M3 13c0-5 4-9 9-9s9 4 9 9v6H3v-6Zm4-3 2 3m2-5 2 3m2-3 2 3M3 16h18',
  pharmacy: 'M8 3h8v5h5v8h-5v5H8v-5H3V8h5V3Z',
  water: 'M3 9h15v5m-11-5V5h8M11 5V2M6 2h10M3 9v5h4v-3m13 6c0 2-1 4-3 4s-3-2-3-4 3-5 3-5 3 3 3 5Z',
  toilet: 'M4 3h3m-3 4h3v6H4V7Zm1.5 6v8m-3 4 3-4 3 4M15 4a2 2 0 1 0 4 0 2 2 0 0 0-4 0Zm0 5h4l2 7h-8l2-7Zm1 7v5m3-5v5',
  aed: 'M12 21S2 15 2 8a5 5 0 0 1 10-2A5 5 0 0 1 22 8c0 7-10 13-10 13Zm1-16-5 8h5l-2 6 6-9h-5l1-5Z',
  charging: 'M4 21V3h12v18H4Zm4-15h4m-2 4-3 5h4l-2 4m7-11h3l2 3v6a2 2 0 0 1-4 0v-4h-1m3-7v3',
  parking: 'M5 21V3h8a5 5 0 0 1 0 10H5m0 0v8',
  bridge: 'M2 17h20M15 3l3 18m-3-18-3 18M15 6 3 15m12-6-7 6m7-3-2 3m3-6 5 6M3 17v4m18-4v4',
  camera: 'm3 5 15 3-2 8L2 13 3 5Zm15 4 4-1-1 7-5-2M9 15v5h8m-3-2v4',
  works: 'M3 10h18v7H3v-7Zm3 0 5 7m2-7 5 7M6 17v5m12-5v5M9 10l2-6h2l2 6',
  route: 'M8 3 5 21m11-18 3 18M12 3v4m0 3v4m0 3v4',
  report: 'M12 3 2 21h20L12 3Zm0 6v5m0 3v1',
  news: 'M5 4h16v15a2 2 0 0 1-2 2H5V4Zm0 4H2v11a2 2 0 0 0 3 2m4-13h8m-8 4h3v4H9v-4Zm6 0h2m-2 4h2',
  leaf: 'M20 4C8 2 2 8 6 15c7 5 15-1 14-11ZM4 21 16 9',
  weather: 'M5 11a4 4 0 0 1 7-5 4 4 0 0 1 7 5 4 4 0 0 1-1 8H6a4 4 0 0 1-1-8ZM4 3l1 2m5-4v2M1 8h2',
  pulse: 'M2 12h5l3-8 4 16 3-8h5',
  pin: 'M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0ZM9 10a3 3 0 1 0 6 0 3 3 0 0 0-6 0Z',
  layers: 'm12 3 10 5-10 5L2 8l10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5',
  search: 'M16 16l5 5M4 10.5a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Z',
  arrow: 'M5 19 19 5M5 5h14v14',
  close: 'm6 6 12 12M6 18 18 6',
  reset: 'M4 10a8 8 0 1 1 2 8M4 4v6h6',
  compass: 'm16 8-3 5-5 3 3-5 5-3ZM3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0Z'
};
ICON_PATHS.spark = ICON_PATHS.event;
ICON_PATHS.ev_charger = ICON_PATHS.charging;
ICON_PATHS.water_tap = ICON_PATHS.water;

const DATASET_KINDS = { events: 'event', districts: 'district', retail: 'shop', amenities: 'pin', traffic: 'route', parking: 'parking', bridges: 'bridge', cameras: 'camera', roadworks: 'works', crowd: 'pulse', emergencies: 'report', news: 'news', environment: 'leaf' };
const SUBTYPES = { concert: 'concert', music: 'concert', festival: 'festival', theatre: 'theatre', theater: 'theatre', musical: 'theatre', exhibition: 'exhibition', stadium_fixture: 'football', football: 'football', supermarket: 'shop', convenience: 'shop', bakery: 'bakery', pharmacy: 'pharmacy', chemist: 'pharmacy', water_tap: 'water', drinking_water: 'water', toilet: 'toilet', public_toilet: 'toilet', aed: 'aed', defibrillator: 'aed', ev_charger: 'charging', charging_station: 'charging', camera: 'camera', webcam: 'camera', surveillance: 'camera', weather_station: 'weather', air_quality: 'leaf' };

export function markerKind(feature) {
  const p = feature?.properties || {};
  const candidates = [p.shop_type, p.subcategory, p.details?.amenity, p.details?.type].map(value => String(value || '').toLowerCase());
  return candidates.map(value => SUBTYPES[value]).find(Boolean) || DATASET_KINDS[p.__dataset] || 'pin';
}
export function markerImageId(kind, selected = false) { return `city-mark-${selected ? 'selected-' : ''}${kind}`; }
export function withMapSymbol(feature) {
  const kind = markerKind(feature);
  return { ...feature, properties: { ...feature.properties, __markerKind: kind, __marker: markerImageId(kind), __selectedMarker: markerImageId(kind, true) } };
}

function accent(kind) {
  if (['event', 'concert', 'festival', 'theatre', 'exhibition', 'football'].includes(kind)) return '#a28a60';
  if (['parking', 'camera', 'weather'].includes(kind)) return '#71888e';
  if (['works', 'bakery'].includes(kind)) return '#a58859';
  if (kind === 'report') return '#aa7d71';
  return '#7b896b';
}

export function markerSvg(kind, selected = false) {
  if (kind === 'cluster' || kind.startsWith('cluster-')) {
    const glyph = kind.slice(8) || 'pin';
    return `<svg xmlns="http://www.w3.org/2000/svg" width="108" height="72" viewBox="0 0 54 36"><path d="M10 5h35l7 7v18l-5 5H10Z" fill="#bfc5ae" stroke="#202a22" stroke-width="2"/><path d="M8 2h37l6 6v18l-6 6H8l-6-6V8Z" fill="#e6e7da" stroke="#202a22" stroke-width="1.5"/><path d="${ICON_PATHS[glyph] || ICON_PATHS.pin}" transform="translate(6 7) scale(.75)" fill="none" stroke="#28332b" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M27 8v18" stroke="#b4baa3" stroke-width="1"/></svg>`;
  }
  const ticket = ['event', 'concert', 'festival', 'theatre', 'exhibition', 'football'].includes(kind);
  const backing = ticket
    ? 'M9 4h22l5 5v6a4 4 0 0 0 0 8v9l-5 5h-7l-4 7-4-7H9l-5-5v-9a4 4 0 0 0 0-8V9l5-5Z'
    : 'M10 4h20l6 6v21l-6 6h-6l-4 7-4-7h-6l-6-6V10l6-6Z';
  const frame = selected ? '<path d="M1 13V8l7-7h5m14 0h5l7 7v5M1 28v5l7 7h5m14 0h5l7-7v-5" fill="none" stroke="#faf7ec" stroke-width="1.7"/>' : '';
  return `<svg xmlns="http://www.w3.org/2000/svg" width="80" height="96" viewBox="0 0 40 48">${frame}<path d="${backing}" fill="#111713" stroke="#111713" stroke-width="4" transform="translate(0 1)"/><path d="${backing}" fill="${selected ? '#eee3c9' : '#e6e7da'}" stroke="#2e382e" stroke-width="1.2"/><path d="${ICON_PATHS[kind] || ICON_PATHS.pin}" transform="translate(9 8) scale(.92)" fill="none" stroke="#28332b" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 32h10" stroke="${accent(kind)}" stroke-width="1.6" stroke-linecap="round"/></svg>`;
}

export function rasterizeSymbol(svg) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
        const context = canvas.getContext('2d', { willReadFrequently: true });
        if (!context) throw new Error('Map symbol canvas is unavailable.');
        context.drawImage(img, 0, 0);
        resolve(context.getImageData(0, 0, canvas.width, canvas.height));
      } catch (error) { reject(error); }
      finally { img.onload = null; img.onerror = null; }
    };
    img.onerror = () => { img.onload = null; img.onerror = null; reject(new Error('Map symbol could not be decoded.')); };
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  });
}

// Decode once per used glyph; reinstall cached pixels after a style swap.
export function createMapSymbolRegistry(map, onReady, decode = rasterizeSymbol) {
  const images = new Map();
  const pending = new Map();
  const owned = new Set();
  let disposed = false;
  function ensure(kind, selected = false) {
    if (disposed) return false;
    const id = markerImageId(kind, selected);
    if (map.hasImage(id)) return true;
    if (images.has(id)) {
      try { map.addImage(id, images.get(id), { pixelRatio: 2 }); owned.add(id); return true; }
      catch (_) { return false; }
    }
    if (!pending.has(id)) {
      const loading = Promise.resolve().then(() => decode(markerSvg(kind, selected))).then(data => {
        if (disposed) return;
        images.set(id, data);
        pending.delete(id);
        onReady();
      }).catch(() => { pending.delete(id); });
      pending.set(id, loading);
    }
    return false;
  }
  return { ensure, destroy() {
    disposed = true;
    // Owned sprites are removed only after the controller's layers detach.
    for (const id of owned) { try { if (map.hasImage(id)) map.removeImage(id); } catch (_) {} }
    images.clear(); pending.clear(); owned.clear();
  } };
}
