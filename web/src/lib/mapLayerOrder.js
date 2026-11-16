/** Ground geometry stays below the atmosphere; glyphs and observed radar stay above it. */
export function firstDataOverlay(layers = []) {
  return layers.find(layer => layer.id === 'live-rain-radar' ||
    (layer.type === 'symbol' && (layer.id.startsWith('explore-') || layer.id.startsWith('explorer-selection'))))?.id;
}
