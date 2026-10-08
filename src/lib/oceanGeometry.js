import earcut from 'earcut';

export const COAST_DISTANCE = 3200;
export const ORIGIN = [4.49, 51.93];
const circumference = 40075016.68557849;
export const METERS_PER_WORLD = circumference * Math.cos(ORIGIN[1] * Math.PI / 180);

export function mercator([lng, lat]) {
  return [(lng + 180) / 360, (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2];
}
export const WORLD_ORIGIN = mercator(ORIGIN);
export function localPoint(coordinate) {
  return mercator(coordinate).map((n, i) => (n - WORLD_ORIGIN[i]) * METERS_PER_WORLD);
}

export function boundaryRing(boundary) {
  const feature = boundary.type === 'FeatureCollection' ? boundary.features[0] : boundary;
  if (feature.geometry.type !== 'Polygon' || feature.geometry.coordinates.length !== 1) {
    throw new Error('Ocean mesh expects one Rotterdam polygon without interior holes.');
  }
  return feature.geometry.coordinates[0].slice(0, -1).map(localPoint);
}

export function fieldBounds(ring) {
  const xs = ring.map(p => p[0]), ys = ring.map(p => p[1]);
  const padding = COAST_DISTANCE + 100;
  return [Math.min(...xs) - padding, Math.min(...ys) - padding,
    Math.max(...xs) + padding, Math.max(...ys) + padding];
}

// A single untiled mesh: outer ocean rectangle with an exact city-shaped hole.
// Local coordinates retain sub-metre precision when the camera is at zoom 20.
export function oceanMesh(ring) {
  const [west, north] = localPoint([-180, 85.0511287798066]);
  const [east, south] = localPoint([180, -85.0511287798066]);
  const points = [[west, north], [east, north], [east, south], [west, south], ...ring];
  const flat = points.flat();
  const indices = earcut(flat, [4], 2);
  return {
    vertices: new Float32Array(flat), indices: new Uint16Array(indices),
    deviation: earcut.deviation(flat, [4], 2, indices)
  };
}

export function polygonMesh(feature) {
  const polygons = feature.geometry.type === 'Polygon' ? [feature.geometry.coordinates] : feature.geometry.coordinates;
  const vertices = [], indices = [];
  for (const polygon of polygons) {
    const flat = earcut.flatten(polygon.map(ring => ring.slice(0, -1).map(localPoint)));
    const offset = vertices.length / 2;
    indices.push(...earcut(flat.vertices, flat.holes, 2).map(i => i + offset));
    vertices.push(...flat.vertices);
  }
  if (vertices.length / 2 > 65535) throw new Error('Ocean geometry exceeds 16-bit indices.');
  return { vertices: new Float32Array(vertices), indices: new Uint16Array(indices) };
}

export function localMatrix(matrix, worldOffset = 0) {
  const result = new Float32Array(16);
  for (let row = 0; row < 4; row++) {
    result[row] = matrix[row] / METERS_PER_WORLD;
    result[4 + row] = matrix[4 + row] / METERS_PER_WORLD;
    result[8 + row] = matrix[8 + row] / METERS_PER_WORLD;
    result[12 + row] = matrix[row] * (WORLD_ORIGIN[0] + worldOffset)
      + matrix[4 + row] * WORLD_ORIGIN[1] + matrix[12 + row];
  }
  return result;
}
