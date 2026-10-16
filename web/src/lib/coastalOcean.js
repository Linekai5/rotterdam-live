import boundary from './rotterdam_boundary.json';
import metadata from './ocean-distance.json';
import distanceUrl from './ocean-distance.png';
import riverBlend from './river-blend.json';
import palette from './ocean-palette.json';
import { boundaryRing, oceanMesh, polygonMesh, localMatrix } from './oceanGeometry.js';

export const OCEAN_LAYER = 'coastal-ocean';
const mesh = oceanMesh(boundaryRing(boundary));
const riverMesh = polygonMesh(riverBlend);
const RIVER_LAYER = 'coastal-river-blend';
let imagePromise;
function distanceImage() {
  if (!imagePromise) {
    imagePromise = new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => { imagePromise = null; reject(new Error('Could not load ocean distance field')); };
      image.src = distanceUrl;
    });
  }
  return imagePromise;
}

const vertexSource = `
  precision highp float;
  attribute vec2 a_position;
  uniform mat4 u_matrix;
  uniform vec4 u_bounds;
  varying highp vec2 v_uv;
  void main() {
    v_uv = (a_position - u_bounds.xy) / (u_bounds.zw - u_bounds.xy);
    gl_Position = u_matrix * vec4(a_position, 0.0, 1.0);
  }
`;
const fragmentSource = `
  precision highp float;
  uniform sampler2D u_distance;
  uniform float u_max_distance;
  uniform float u_river_blend;
  varying highp vec2 v_uv;
  void main() {
    vec3 coast = vec3(${palette.coast.map(value => value.toFixed(1)).join(', ')}) / 255.0;
    vec3 ocean = vec3(${palette.ocean.map(value => value.toFixed(1)).join(', ')}) / 255.0;
    vec2 encodedDistance = texture2D(u_distance, clamp(v_uv, 0.0, 1.0)).rg;
    float distance = dot(encodedDistance, vec2(65280.0, 255.0)) / 65535.0 * u_max_distance;
    if (u_river_blend > 0.5) {
      float alpha = 1.0 - smoothstep(20.0, ${riverBlend.properties.transitionMeters.toFixed(1)}, distance);
      gl_FragColor = vec4(coast * alpha, alpha);
      return;
    }
    // A short flat coast also absorbs interpolation error in the distance field.
    float t = clamp((distance - 30.0) / (u_max_distance - 30.0), 0.0, 1.0);
    t = 1.0 - (1.0 - t) * (1.0 - t);
    vec3 color = mix(coast, ocean, t);
    // Sub-LSB dithering avoids visible 8-bit color bands; endpoints stay exact.
    float noise = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) - 0.5;
    color += noise / 255.0 * (4.0 * t * (1.0 - t));
    gl_FragColor = vec4(color, 1.0);
  }
`;

function shader(gl, type, source) {
  const value = gl.createShader(type);
  gl.shaderSource(value, source);
  gl.compileShader(value);
  if (!gl.getShaderParameter(value, gl.COMPILE_STATUS)) {
    const message = gl.getShaderInfoLog(value);
    gl.deleteShader(value);
    throw new Error(message);
  }
  return value;
}

class CoastalOcean {
  id = OCEAN_LAYER;
  type = 'custom';
  renderingMode = '2d';
  constructor(image, river = false) {
    this.image = image;
    this.river = river;
    this.mesh = river ? riverMesh : mesh;
    this.id = river ? RIVER_LAYER : OCEAN_LAYER;
  }

  initialize(gl) {
    const vertex = shader(gl, gl.VERTEX_SHADER, vertexSource);
    const fragment = shader(gl, gl.FRAGMENT_SHADER, fragmentSource);
    this.program = gl.createProgram();
    gl.attachShader(this.program, vertex);
    gl.attachShader(this.program, fragment);
    gl.linkProgram(this.program);
    gl.deleteShader(vertex);
    gl.deleteShader(fragment);
    if (!gl.getProgramParameter(this.program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(this.program));
    this.position = gl.getAttribLocation(this.program, 'a_position');
    this.uniforms = Object.fromEntries(['matrix', 'bounds', 'distance', 'max_distance', 'river_blend']
      .map(name => [name, gl.getUniformLocation(this.program, `u_${name}`)]));
    this.vertices = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.vertices);
    gl.bufferData(gl.ARRAY_BUFFER, this.mesh.vertices, gl.STATIC_DRAW);
    this.indices = gl.createBuffer();
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.indices);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, this.mesh.indices, gl.STATIC_DRAW);
    this.texture = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, this.image);
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.BROWSER_DEFAULT_WEBGL);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  }

  onAdd(map, gl) {
    this.initialize(gl);
  }

  render(gl, matrix) {
    gl.useProgram(this.program);
    gl.disable(gl.CULL_FACE);
    gl.disable(gl.DEPTH_TEST);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.vertices);
    gl.enableVertexAttribArray(this.position);
    gl.vertexAttribPointer(this.position, 2, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.indices);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    gl.uniform1i(this.uniforms.distance, 0);
    gl.uniform4fv(this.uniforms.bounds, metadata.bounds);
    gl.uniform1f(this.uniforms.max_distance, metadata.maxDistance);
    gl.uniform1f(this.uniforms.river_blend, this.river ? 1 : 0);
    gl.uniformMatrix4fv(this.uniforms.matrix, false, localMatrix(matrix));
    gl.drawElements(gl.TRIANGLES, this.mesh.indices.length, gl.UNSIGNED_SHORT, 0);
  }

  onRemove(map, gl) {
    if (gl.isBuffer(this.vertices)) gl.deleteBuffer(this.vertices);
    if (gl.isBuffer(this.indices)) gl.deleteBuffer(this.indices);
    if (gl.isTexture(this.texture)) gl.deleteTexture(this.texture);
    if (gl.isProgram(this.program)) gl.deleteProgram(this.program);
  }
}

// Load once, then restore on every satellite style load. The blue mask stays in
// place until the shader is ready, including when switching styles rapidly.
export function removeCoastalOcean(map) {
  // MapLibre 2.x omits custom layers from serialized styles, so style diffing
  // cannot remove them when moving from satellite to another map mode.
  for (const id of [RIVER_LAYER, OCEAN_LAYER]) {
    if (map.getLayer(id)) map.removeLayer(id);
  }
}

export function installCoastalOcean(map) {
  let removed = false;
  let pending = false;
  let restoreStyle = null;
  // MapLibre 2.4 retains stale tile GPU buffers after context loss. Dispose
  // while the context is lost, then rebuild the style and both custom layers.
  const contextLost = () => {
    restoreStyle = map.getStyle();
    const mask = restoreStyle?.layers.find(layer => layer.id === 'rotterdam-water-mask');
    if (mask) mask.layout = { ...mask.layout, visibility: 'visible' };
    removeCoastalOcean(map);
    // Keep an empty style for any already queued camera/render callbacks.
    map.setStyle({ version: 8, sources: {}, layers: [] }, { diff: false });
  };
  const contextRestored = () => {
    if (restoreStyle) map.setStyle(restoreStyle, { diff: false });
    restoreStyle = null;
  };
  const update = async () => {
    if (removed || pending || !map.getStyle() || !map.getLayer('satellite-layer') || map.getLayer(OCEAN_LAYER)) return;
    pending = true;
    try {
      const image = await distanceImage();
      if (removed || !map.getStyle() || !map.getLayer('satellite-layer') || map.getLayer(OCEAN_LAYER)) return;
      const firstLabel = map.getStyle().layers.find(layer => layer.type === 'symbol')?.id;
      const weatherLayerId = map.getLayer('rotterdam-volumetric-weather') ? 'rotterdam-volumetric-weather' : undefined;
      map.addLayer(new CoastalOcean(image, true), firstLabel || weatherLayerId);
      map.addLayer(new CoastalOcean(image), weatherLayerId);
      map.setLayoutProperty('rotterdam-water-mask', 'visibility', 'none');
    } catch (error) {
      if (map.getLayer(OCEAN_LAYER)) map.removeLayer(OCEAN_LAYER);
      if (map.getLayer(RIVER_LAYER)) map.removeLayer(RIVER_LAYER);
      console.error('Coastal ocean unavailable; keeping the ocean mask.', error);
    } finally {
      pending = false;
    }
  };
  map.on('styledata', update);
  map.on('webglcontextlost', contextLost);
  map.on('webglcontextrestored', contextRestored);
  map.once('remove', () => {
    removed = true;
    map.off('styledata', update);
    map.off('webglcontextlost', contextLost);
    map.off('webglcontextrestored', contextRestored);
  });
}
