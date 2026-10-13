import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { PNG } from 'pngjs';
import { boundaryRing, fieldBounds, COAST_DISTANCE } from '../src/lib/oceanGeometry.js';

const boundaryFile = new URL('../src/lib/rotterdam_boundary.json', import.meta.url);
const boundaryBytes = readFileSync(boundaryFile);
const ring = boundaryRing(JSON.parse(boundaryBytes));
const bounds = fieldBounds(ring);
const size = 1024;
const segments = ring.map((a, i) => ({ a, b: ring[(i + 1) % ring.length] }));

// A bounding-volume tree makes exact point-to-segment distances inexpensive.
function tree(parts) {
  const points = parts.flatMap(s => [s.a, s.b]);
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const box = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  if (parts.length <= 8) return { box, parts };
  const axis = box[2] - box[0] > box[3] - box[1] ? 0 : 1;
  parts.sort((s, t) => s.a[axis] + s.b[axis] - t.a[axis] - t.b[axis]);
  const mid = Math.floor(parts.length / 2);
  return { box, children: [tree(parts.slice(0, mid)), tree(parts.slice(mid))] };
}
function boxDistance(x, y, box) {
  return Math.max(box[0] - x, 0, x - box[2]) ** 2
    + Math.max(box[1] - y, 0, y - box[3]) ** 2;
}
function nearest(x, y, node, best) {
  if (boxDistance(x, y, node.box) >= best) return best;
  if (node.parts) {
    for (const { a, b } of node.parts) {
      const dx = b[0] - a[0], dy = b[1] - a[1];
      const length = dx * dx + dy * dy;
      const t = length ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / length)) : 0;
      best = Math.min(best, (x - a[0] - t * dx) ** 2 + (y - a[1] - t * dy) ** 2);
    }
    return best;
  }
  let [a, b] = node.children;
  if (boxDistance(x, y, a.box) > boxDistance(x, y, b.box)) [a, b] = [b, a];
  return nearest(x, y, b, nearest(x, y, a, best));
}
const root = tree(segments);
const png = new PNG({ width: size, height: size });
for (let y = 0; y < size; y++) {
  for (let x = 0; x < size; x++) {
    const px = bounds[0] + (x + 0.5) / size * (bounds[2] - bounds[0]);
    const py = bounds[1] + (y + 0.5) / size * (bounds[3] - bounds[1]);
    const distance = Math.sqrt(nearest(px, py, root, COAST_DISTANCE ** 2));
    const encoded = Math.round(distance / COAST_DISTANCE * 65535);
    const index = (y * size + x) * 4;
    png.data[index] = encoded >> 8;
    png.data[index + 1] = encoded & 255;
    png.data[index + 2] = 0;
    png.data[index + 3] = 255;
  }
}
writeFileSync(new URL('../src/lib/ocean-distance.png', import.meta.url), PNG.sync.write(png));
writeFileSync(new URL('../src/lib/ocean-distance.json', import.meta.url), JSON.stringify({
  bounds, size, maxDistance: COAST_DISTANCE,
  boundaryHash: createHash('sha256').update(boundaryBytes).digest('hex')
}, null, 2) + '\n');
console.log(`Generated ${size}×${size} ocean distance field; shoreline remains vector geometry.`);
