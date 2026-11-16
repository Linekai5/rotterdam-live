export const MAX_ZOOM_LIMIT = 19.5;
export const URBAN_COVERAGE_BOUNDS = [[4.379, 51.861], [4.602, 51.995]];
const OVERVIEW_PADDING = 40;
const OVERVIEW_ZOOM_OUT = 0.35;
const PAN_MARGIN = 0.12;

const mercatorY = latitude => (1 - Math.log(Math.tan(Math.PI / 4 + latitude * Math.PI / 360)) / Math.PI) / 2;
const latitudeAt = y => Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180 / Math.PI;

/** Keep the city fit independent of the navigation fence and viewport shape. */
export function calculateCameraLimits(container = null, coverage = URBAN_COVERAGE_BOUNDS) {
  const width = Math.max(160, container?.clientWidth || (typeof window !== 'undefined' ? window.innerWidth : 1440) || 1440);
  const height = Math.max(160, container?.clientHeight || (typeof window !== 'undefined' ? window.innerHeight : 900) || 900);
  const [[west, south], [east, north]] = coverage;
  const cityWidth = (east - west) / 360;
  const cityHeight = mercatorY(south) - mercatorY(north);
  const padding = Math.min(OVERVIEW_PADDING, width / 8, height / 8);
  const fitZoom = Math.log2(Math.min((width - padding * 2) / (512 * cityWidth), (height - padding * 2) / (512 * cityHeight)));
  const minZoom = fitZoom - OVERVIEW_ZOOM_OUT;
  const scale = 512 * 2 ** minZoom;
  const centerX = (west + east + 360) / 720;
  const centerY = (mercatorY(south) + mercatorY(north)) / 2;
  const halfWidth = width / scale / 2 * (1 + PAN_MARGIN * 2);
  const halfHeight = height / scale / 2 * (1 + PAN_MARGIN * 2);
  return {
    minZoom, fitZoom, padding,
    center: [centerX * 360 - 180, latitudeAt(centerY)],
    navigationBounds: [
      [(centerX - halfWidth) * 360 - 180, latitudeAt(centerY + halfHeight)],
      [(centerX + halfWidth) * 360 - 180, latitudeAt(centerY - halfHeight)]
    ]
  };
}

/**
 * Allow a small zoom-out beyond a genuine full-city fit at every aspect ratio.
 *
 * @param {HTMLElement | { clientWidth?: number, clientHeight?: number } | null} container
 * @returns {number} Minimum zoom, relative to the actual city fit.
 */
export function calculateResponsiveMinZoom(container = null) {
  return calculateCameraLimits(container).minZoom;
}

export function installResponsiveMinZoom(map) {
  let lastSize = '';
  const update = () => {
    const container = map.getContainer();
    const size = `${container?.clientWidth}:${container?.clientHeight}`;
    if (size === lastSize) return;
    lastSize = size;
    const limits = calculateCameraLimits(container);
    // Native constraints only: no recursive camera corrections during gestures.
    map.setMaxBounds(limits.navigationBounds);
    map.setMinZoom(limits.minZoom);
  };
  update();
  map.on('resize', update);
  map.once('remove', () => map.off('resize', update));
}
