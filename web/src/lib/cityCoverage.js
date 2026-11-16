import boundary from './rotterdam_boundary.json' with { type: 'json' };
import { bbox, booleanIntersects, booleanPointInPolygon, featureCollection, intersect, lineSplit, lineString } from '@turf/turf';
import { URBAN_COVERAGE_BOUNDS } from './cameraPhysics.js';

const city = boundary.features?.[0] || boundary;
const cache = new WeakMap();
const presence = new WeakMap();
const shapePresence = new Map();
const shapeCoverage = new Map();
const MAX_SHAPES = 64;
const [[west, south], [east, north]] = URBAN_COVERAGE_BOUNDS;

/** Navigation allowance is deliberately larger than the supplied map footprint. */
export function pointIsInCity(coordinates) {
  if (!Array.isArray(coordinates) || coordinates.length < 2) return false;
  const [x, y] = coordinates;
  return Number.isFinite(x) && Number.isFinite(y) && x >= west && x <= east && y >= south && y <= north
    && booleanPointInPolygon([x, y], city);
}

function remember(map, key, value) {
  map.set(key, value);
  if (map.size > MAX_SHAPES) map.delete(map.keys().next().value);
  return value;
}

export function featureHasCityCoverage(featureOrGeometry) {
  const geometry = featureOrGeometry?.type === 'Feature' ? featureOrGeometry.geometry : featureOrGeometry;
  if (!geometry || typeof geometry !== 'object') return false;
  if (presence.has(geometry)) return presence.get(geometry);
  let result = false;
  try {
    if (geometry.type === 'Point') result = pointIsInCity(geometry.coordinates);
    else if (geometry.type === 'MultiPoint') result = geometry.coordinates.some(pointIsInCity);
    else if (['LineString', 'MultiLineString', 'Polygon', 'MultiPolygon'].includes(geometry.type)) {
      const key = JSON.stringify(geometry);
      if (shapePresence.has(key)) result = shapePresence.get(key);
      else {
        const box = bbox(geometry);
        result = box.every(Number.isFinite) && box[2] >= west && box[0] <= east && box[3] >= south && box[1] <= north
          && booleanIntersects({ type: 'Feature', geometry, properties: {} }, city);
        remember(shapePresence, key, result);
      }
    }
  } catch { /* Invalid geometry remains a readable, unmapped source record. */ }
  presence.set(geometry, result);
  return result;
}

function visibleLines(coordinates) {
  const visible = [];
  for (const line of coordinates) {
    const input = lineString(line);
    const split = lineSplit(input, city).features;
    for (const part of split.length ? split : [input]) {
      const points = part.geometry.coordinates;
      // After boundary splitting, a non-zero segment midpoint determines which
      // side a piece lies on. No synthetic path or visual offset is introduced.
      for (let index = 1; index < points.length; index++) {
        const a = points[index - 1], b = points[index];
        if (a[0] === b[0] && a[1] === b[1]) continue;
        if (pointIsInCity([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2])) visible.push(points);
        break;
      }
    }
  }
  return visible.length ? { type: visible.length === 1 ? 'LineString' : 'MultiLineString', coordinates: visible.length === 1 ? visible[0] : visible } : null;
}

function coverageGeometry(geometry) {
  if (geometry.type === 'Point') return pointIsInCity(geometry.coordinates) ? geometry : null;
  if (geometry.type === 'MultiPoint') {
    const coordinates = geometry.coordinates.filter(pointIsInCity);
    return coordinates.length ? { ...geometry, coordinates } : null;
  }
  if (geometry.type === 'LineString') return visibleLines([geometry.coordinates]);
  if (geometry.type === 'MultiLineString') return visibleLines(geometry.coordinates);
  if (geometry.type === 'Polygon' || geometry.type === 'MultiPolygon') {
    return intersect(featureCollection([city, { type: 'Feature', geometry, properties: {} }]))?.geometry || null;
  }
  return null;
}

export function cityCoverage(featureOrGeometry) {
  const geometry = featureOrGeometry?.type === 'Feature' ? featureOrGeometry.geometry : featureOrGeometry;
  if (!geometry || typeof geometry !== 'object') return null;
  if (cache.has(geometry)) return cache.get(geometry);
  if (!featureHasCityCoverage(geometry)) { cache.set(geometry, null); return null; }
  let result = null;
  try {
    const key = geometry.type === 'Point' ? null : JSON.stringify(geometry);
    if (key && shapeCoverage.has(key)) { result = shapeCoverage.get(key); cache.set(geometry, result); return result; }
    const visible = coverageGeometry(geometry);
    if (visible) result = { geometry: visible, bounds: bbox(visible) };
    if (key) remember(shapeCoverage, key, result);
  } catch {
    // Invalid source geometry can remain readable as a record, but cannot be
    // treated as a mapped place or become an unsafe camera target.
  }
  cache.set(geometry, result);
  return result;
}

export function featureForCityMap(feature) {
  if (!featureHasCityCoverage(feature)) return null;
  // Area outlines retain the original boundary and are occluded by the city
  // mask. Stroking an intersected polygon would invent borders at the cut.
  return feature.geometry.type === 'MultiPoint' ? { ...feature, geometry: { ...feature.geometry, coordinates: feature.geometry.coordinates.filter(pointIsInCity) } } : feature;
}
