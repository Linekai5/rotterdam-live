export const MAX_ZOOM_LIMIT = 19.5;

/**
 * Calculate the preferred minimum zoom from the viewport dimensions.
 * MapLibre can apply a higher zoom to keep the viewport within the tile bounds.
 *
 * @param {HTMLElement | { clientWidth?: number, clientHeight?: number } | null} container
 * @returns {number} Responsive minZoom in [10.6, 11.2]
 */
export function calculateResponsiveMinZoom(container = null) {
  const width = container?.clientWidth || (typeof window !== 'undefined' ? window.innerWidth : 1440) || 1440;
  const height = container?.clientHeight || (typeof window !== 'undefined' ? window.innerHeight : 900) || 900;
  const aspect = width / Math.max(1, height);

  const baseZoom = 10.85 + Math.log2(Math.max(320, width) / 1366) * 0.35;
  const aspectAdjustment = aspect < 1.0 ? -0.18 : (aspect > 2.0 ? 0.12 : 0.0);
  const computed = baseZoom + aspectAdjustment;

  return Math.max(10.6, Math.min(11.2, Number(computed.toFixed(2))));
}

export function installResponsiveMinZoom(map) {
  const update = () => map.setMinZoom(calculateResponsiveMinZoom(map.getContainer()));
  map.on('resize', update);
  map.once('remove', () => map.off('resize', update));
}
