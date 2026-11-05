/**
 * Elastic "Auto Snap-Back" Island Boundary Physics & Responsive Zoom Clamping
 * for Rotterdam Island (Maasvlakte / Hoek van Holland [3.93, 51.83] to Nesselande [4.63, 52.01]).
 */

export const ROTTERDAM_ISLAND_SW = [3.93, 51.83];
export const ROTTERDAM_ISLAND_NE = [4.63, 52.01];

/**
 * Buffered bounding envelope of Rotterdam Island [SW, NE]
 */
export const ROTTERDAM_ISLAND_ENVELOPE = [
  ROTTERDAM_ISLAND_SW,
  ROTTERDAM_ISLAND_NE
];

/**
 * Generous outer safety maxBounds so the user can drag slightly into the
 * abyssal water margin with natural resistance before hitting any hard stop.
 */
export const ROTTERDAM_OUTER_SAFETY_BOUNDS = [
  [3.72, 51.74],
  [4.84, 52.10]
];

/**
 * Convex polygon ring enclosing Rotterdam Island from Maasvlakte / Hoek van Holland
 * in the west to Nesselande / Kralingse Bos / IJsselmonde in the east.
 * Counter-clockwise closed ring [lng, lat].
 */
export const ROTTERDAM_ISLAND_POLYGON = [
  [3.93, 51.90], // Maasvlakte West
  [4.15, 51.83], // Rozenburg / Europoort South
  [4.50, 51.83], // Charlois / Zuidrand South
  [4.63, 51.88], // IJsselmonde / Ridderkerk East
  [4.63, 52.00], // Nesselande / Prins Alexander North-East
  [4.50, 52.01], // Hillegersberg / Schiebroek North
  [4.12, 52.01], // Hoek van Holland North
  [3.93, 51.98], // Maasvlakte North-West
  [3.93, 51.90]  // Close ring
];

export const MAX_ZOOM_LIMIT = 19.5;
export const SNAP_BACK_DURATION_MS = 750;

/**
 * Critically-damped cubic-out easing curve: f(t) = 1 - (1 - t)^3
 * @param {number} t Normalized time [0..1]
 * @returns {number} Eased progress [0..1]
 */
export function cubicOutEasing(t) {
  const clamped = Math.max(0, Math.min(1, t));
  return 1 - Math.pow(1 - clamped, 3);
}

/**
 * Calculate responsive minZoom (clamped between 10.6 and 11.2) based on viewport
 * dimensions and aspect ratio so Rotterdam Island fills the viewport comfortably
 * at maximum zoom-out without shrinking into a tiny speck.
 *
 * @param {HTMLElement | { clientWidth?: number, clientHeight?: number } | null} container
 * @returns {number} Responsive minZoom in [10.6, 11.2]
 */
export function calculateResponsiveMinZoom(container = null) {
  const width = container?.clientWidth || (typeof window !== 'undefined' ? window.innerWidth : 1440) || 1440;
  const height = container?.clientHeight || (typeof window !== 'undefined' ? window.innerHeight : 900) || 900;
  const aspect = width / Math.max(1, height);

  // Span of Rotterdam Island core ~ 0.65° longitude.
  // Scale zoom logarithmically with viewport width and adjust for portrait/ultrawide aspect ratios.
  const baseZoom = 10.85 + Math.log2(Math.max(320, width) / 1366) * 0.35;
  const aspectAdjustment = aspect < 1.0 ? -0.18 : (aspect > 2.0 ? 0.12 : 0.0);
  const computed = baseZoom + aspectAdjustment;

  return Math.max(10.6, Math.min(11.2, Number(computed.toFixed(2))));
}

/**
 * Ray-casting point-in-polygon check for Rotterdam Island convex polygon + envelope.
 * @param {number} lng Longitude
 * @param {number} lat Latitude
 * @returns {boolean} True if inside valid Rotterdam Island bounds
 */
export function isPointInRotterdamIsland(lng, lat) {
  if (
    lng < ROTTERDAM_ISLAND_SW[0] ||
    lng > ROTTERDAM_ISLAND_NE[0] ||
    lat < ROTTERDAM_ISLAND_SW[1] ||
    lat > ROTTERDAM_ISLAND_NE[1]
  ) {
    return false;
  }

  let inside = false;
  const ring = ROTTERDAM_ISLAND_POLYGON;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];

    const intersect =
      yi > lat !== yj > lat &&
      lng < ((xj - xi) * (lat - yi)) / (yj - yi + 1e-12) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

/**
 * Find the nearest valid point on the Rotterdam Island frontier for a camera center (lng, lat).
 * Uses aspect-corrected Euclidean projection in Rotterdam's local latitude (cos(51.92°)).
 *
 * @param {number} lng Camera center longitude
 * @param {number} lat Camera center latitude
 * @returns {{ lng: number, lat: number, outside: boolean, distanceDeg: number }}
 */
export function clampToRotterdamIsland(lng, lat) {
  if (isPointInRotterdamIsland(lng, lat)) {
    return { lng, lat, outside: false, distanceDeg: 0 };
  }

  const cosLat = Math.cos((51.92 * Math.PI) / 180); // ~0.6168
  const ring = ROTTERDAM_ISLAND_POLYGON;

  let bestLng = Math.max(ROTTERDAM_ISLAND_SW[0], Math.min(ROTTERDAM_ISLAND_NE[0], lng));
  let bestLat = Math.max(ROTTERDAM_ISLAND_SW[1], Math.min(ROTTERDAM_ISLAND_NE[1], lat));
  let minDistSq = Infinity;

  for (let i = 0; i < ring.length - 1; i++) {
    const ax = ring[i][0], ay = ring[i][1];
    const bx = ring[i + 1][0], by = ring[i + 1][1];

    const dx = (bx - ax) * cosLat;
    const dy = by - ay;
    const lenSq = dx * dx + dy * dy;

    let t = 0;
    if (lenSq > 1e-12) {
      const px = (lng - ax) * cosLat;
      const py = lat - ay;
      t = Math.max(0, Math.min(1, (px * dx + py * dy) / lenSq));
    }

    const projLng = ax + t * (bx - ax);
    const projLat = ay + t * (by - ay);

    const errX = (lng - projLng) * cosLat;
    const errY = lat - projLat;
    const distSq = errX * errX + errY * errY;

    if (distSq < minDistSq) {
      minDistSq = distSq;
      bestLng = projLng;
      bestLat = projLat;
    }
  }

  // Nudge 0.8% toward Rotterdam Island centroid [4.42, 51.92] so the snapped camera
  // rests cleanly inside the valid polygon and avoids boundary jitter.
  const centroidLng = 4.42;
  const centroidLat = 51.92;
  const targetLng = Number((bestLng + (centroidLng - bestLng) * 0.015).toFixed(6));
  const targetLat = Number((bestLat + (centroidLat - bestLat) * 0.015).toFixed(6));

  return {
    lng: targetLng,
    lat: targetLat,
    outside: true,
    distanceDeg: Math.sqrt(minDistSq)
  };
}

/**
 * Attach the elastic "auto snap-back" physics controller and responsive minZoom
 * handler to a MapLibre GL instance.
 *
 * @param {import('maplibre-gl').Map} map
 * @returns {() => void} Cleanup function
 */
export function installElasticIslandPhysics(map) {
  if (!map) return () => {};

  let isSnappingBack = false;
  let isUserDragging = false;

  const triggerElasticSnapBack = () => {
    if (isSnappingBack || isUserDragging) return;

    const center = map.getCenter();
    const clamped = clampToRotterdamIsland(center.lng, center.lat);

    if (clamped.outside && clamped.distanceDeg > 0.0002) {
      isSnappingBack = true;
      map.easeTo({
        center: [clamped.lng, clamped.lat],
        duration: typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : SNAP_BACK_DURATION_MS,
        easing: cubicOutEasing,
        essential: false
      });
    }
  };

  const onDragStart = () => {
    isUserDragging = true;
    isSnappingBack = false;
  };

  const onDragEnd = () => {
    isUserDragging = false;
    triggerElasticSnapBack();
  };

  const onMove = () => {
    // If camera is coasting on post-drag inertia far into the abyssal water margin,
    // intercept early and trigger elastic snap-back so inertia feels damped.
    if (!isUserDragging && !isSnappingBack) {
      const center = map.getCenter();
      const clamped = clampToRotterdamIsland(center.lng, center.lat);
      if (clamped.outside && clamped.distanceDeg > 0.04) {
        triggerElasticSnapBack();
      }
    }
  };

  const onMoveEnd = () => {
    if (isSnappingBack) {
      isSnappingBack = false;
      // Verify final position is inside island bounds
      const center = map.getCenter();
      const check = clampToRotterdamIsland(center.lng, center.lat);
      if (check.outside && check.distanceDeg > 0.001) {
        triggerElasticSnapBack();
      }
      return;
    }
    triggerElasticSnapBack();
  };

  const onResize = () => {
    try {
      const container = map.getContainer();
      const newMinZoom = calculateResponsiveMinZoom(container);
      map.setMinZoom(newMinZoom);
      if (map.getZoom() < newMinZoom) {
        map.easeTo({ zoom: newMinZoom, duration: 350, easing: cubicOutEasing });
      }
    } catch (_) {}
  };

  map.on('dragstart', onDragStart);
  map.on('dragend', onDragEnd);
  map.on('move', onMove);
  map.on('moveend', onMoveEnd);
  map.on('resize', onResize);

  const cleanup = () => {
    map.off('dragstart', onDragStart);
    map.off('dragend', onDragEnd);
    map.off('move', onMove);
    map.off('moveend', onMoveEnd);
    map.off('resize', onResize);
  };

  map.once('remove', cleanup);
  return cleanup;
}
