/**
 * Live-source weather controller and MapLibre cloud/radar rendering for Rotterdam.
 *
 * The validated 12-node model grid is interpolated from a GPU data texture.
 * Two continuous 3D density fields use 16 depth samples each, solar self-shadow
 * probes, transmission, and premultiplied-alpha compositing. Low/middle cover
 * share a lower visual deck; high cover drives an upper deck. Heights and camera
 * projection are illustrative. Model 10m wind drives drift; zoom fades the canopy.
 *
 * Observed rain is a separate RainViewer raster layer with frame-age checks.
 * No runtime weather presets, synthetic initial weather, or random lightning.
 * Model effects require fresh accepted data. Reduced-resolution rendering and
 * a 33ms idle repaint timer limit cost; frame rate depends on the device.
 * See rotterdam_live_api_architecture.txt for contracts and known limitations.
 */

import { ORIGIN, WORLD_ORIGIN, METERS_PER_WORLD, mercator, localPoint, localMatrix } from './oceanGeometry.js';

export const WEATHER_LAYER_ID = 'rotterdam-volumetric-weather';

const ISLAND_DISTANCE_BOUNDS = [
  -10898.04410184292,
  -10460.0233404718,
  10974.834178106921,
  10900.988901952896
];
const ISLAND_MAX_DISTANCE = 3200;
const distanceUrl = new URL('./ocean-distance.png', import.meta.url).href;

const DEFAULT_API_BASE = import.meta.env?.DEV ? '' : typeof window !== 'undefined'
  ? (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
      ? 'http://localhost:8000'
      : '')
  : 'http://localhost:8000';

const WEATHER_API_BASE_URL = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL !== undefined)
  ? import.meta.env.VITE_API_BASE_URL
  : DEFAULT_API_BASE;


/**
 * Canonical 12-Point Spatial Weather Micro-Grid spanning Rotterdam Island
 */
export const ROTTERDAM_WEATHER_NODES = [
  { node_id: 1, id: 'weather-grid-node-1', name: 'Maasvlakte West', zone: 'coastal', lat: 51.958, lon: 3.985 },
  { node_id: 2, id: 'weather-grid-node-2', name: 'Hoek van Holland', zone: 'coastal', lat: 51.977, lon: 4.133 },
  { node_id: 3, id: 'weather-grid-node-3', name: 'Rozenburg / Botlek', zone: 'harbor', lat: 51.888, lon: 4.245 },
  { node_id: 4, id: 'weather-grid-node-4', name: 'Vlaardingen / Schiedam Border', zone: 'river', lat: 51.915, lon: 4.355 },
  { node_id: 5, id: 'weather-grid-node-5', name: 'Pernis / Waalhaven', zone: 'harbor', lat: 51.885, lon: 4.415 },
  { node_id: 6, id: 'weather-grid-node-6', name: 'Delfshaven / Noord', zone: 'urban', lat: 51.928, lon: 4.448 },
  { node_id: 7, id: 'weather-grid-node-7', name: 'Rotterdam Centrum', zone: 'urban', lat: 51.922, lon: 4.479 },
  { node_id: 8, id: 'weather-grid-node-8', name: 'Charlois / Zuiderpark', zone: 'urban', lat: 51.882, lon: 4.482 },
  { node_id: 9, id: 'weather-grid-node-9', name: 'Kralingen / Crooswijk', zone: 'inland', lat: 51.932, lon: 4.522 },
  { node_id: 10, id: 'weather-grid-node-10', name: 'Hillegersberg / Schiebroek', zone: 'inland', lat: 51.962, lon: 4.485 },
  { node_id: 11, id: 'weather-grid-node-11', name: 'Feijenoord / IJsselmonde', zone: 'river', lat: 51.888, lon: 4.545 },
  { node_id: 12, id: 'weather-grid-node-12', name: 'Prins Alexander / Nesselande', zone: 'inland', lat: 51.965, lon: 4.575 }
];

/**
 * Compute smooth Inverse Distance Weighted (IDW) weather metrics at any (lng, lat)
 * across the 12-node Rotterdam Island weather grid.
 *
 * @param {number} lng Longitude
 * @param {number} lat Latitude
 * @param {Array<Object>} nodes 12-node telemetry array
 * @returns {Object} Interpolated meteorological metrics at (lng, lat)
 */
export function interpolateWeatherAtPoint(lng, lat, nodes = []) {
  if (!nodes?.length) return null;
  const activeNodes = nodes;
  const cosLat = Math.cos((51.92 * Math.PI) / 180);

  let weightSum = 0;
  let cloudLow = 0;
  let cloudMid = 0;
  let cloudHigh = 0;
  let precip = 0;
  let windU = 0;
  let windV = 0;
  let storm = 0;
  let fog = 0;
  let temp = 0;

  for (let i = 0; i < activeNodes.length; i++) {
    const n = activeNodes[i];
    const dx = (lng - n.lon) * cosLat;
    const dy = lat - n.lat;
    const distSq = dx * dx + dy * dy + 0.00018;
    const w = 1.0 / (distSq * Math.sqrt(distSq)); // p = 3 IDW kernel

    weightSum += w;
    cloudLow += (n.cloud_cover_low ?? 30) * w;
    cloudMid += (n.cloud_cover_mid ?? 20) * w;
    cloudHigh += (n.cloud_cover_high ?? 10) * w;
    precip += (n.precipitation ?? 0) * w;
    windU += (n.wind_u ?? 3.0) * w;
    windV += (n.wind_v ?? 2.0) * w;
    storm += (n.storm_intensity ?? 0) * w;
    fog += (n.fog_density ?? 0) * w;
    temp += (n.temperature_2m ?? 16) * w;
  }

  const inv = weightSum > 0 ? 1.0 / weightSum : 1.0;
  return {
    cloud_cover_low: cloudLow * inv,
    cloud_cover_mid: cloudMid * inv,
    cloud_cover_high: cloudHigh * inv,
    precipitation: precip * inv,
    wind_u: windU * inv,
    wind_v: windV * inv,
    storm_intensity: storm * inv,
    fog_density: fog * inv,
    temperature_2m: temp * inv
  };
}

/**
 * Phase 4 Altitude Zoom-Fade ("Dive Through the Clouds" Mechanics):
 * - Macro Island View (zoom 10.6 to 12.2): full volumetric cloud opacity (up to 0.85-0.95)
 * - Cloud Penetration Transition (zoom 12.2 to 14.2): smoothstep(14.2, 12.0, zoom) + radial camera parting
 * - Street / Tactical View (zoom > 14.2): upper cloud canopy <= 0.04 so streets & buildings are razor-sharp
 *
 * @param {number} zoom Current MapLibre camera zoom
 * @param {number} radialNdcDist Normalized radial distance from screen center [0..1.414]
 * @returns {{ canopyOpacity: number, shadowStrength: number, streetWetness: number, phaseLabel: string }}
 */
export function computeAltitudeCloudFade(zoom, radialNdcDist = 0.5) {
  const smoothstep = (edge0, edge1, x) => {
    const t = Math.max(0, Math.min(1, (x - edge0) / (edge1 - edge0)));
    return t * t * (3 - 2 * t);
  };

  // smoothstep(14.2, 12.0, zoom): 1.0 at zoom <= 12.0, 0.0 at zoom >= 14.2
  const baseAltitudeAlpha = smoothstep(14.2, 12.0, zoom);

  // Radial parting effect during cloud penetration (zoom 12.0 -> 14.2)
  const penetrationProgress = smoothstep(11.9, 14.2, zoom);
  const radialParting = 1.0 - penetrationProgress * (1.0 - smoothstep(0.0, 0.95, radialNdcDist)) * 0.65;

  // Floor at 0.025 in street view so subtle atmospheric movement remains while <= 0.04
  const canopyOpacity = Math.max(0.025, Math.min(0.95, baseAltitudeAlpha * radialParting * 0.93 + 0.025 * (1 - baseAltitudeAlpha)));

  // Ground cloud shadows stay visible in macro & descent, softly modulating at street level
  const shadowStrength = 0.22 + 0.78 * smoothstep(16.0, 11.8, zoom);

  // Wet surface specular shimmer activates when zoomed in (zoom > 13.5)
  const streetWetness = smoothstep(13.4, 15.0, zoom);

  let phaseLabel = 'MACRO CANOPY';
  if (zoom > 14.2) {
    phaseLabel = 'STREET TACTICAL';
  } else if (zoom > 12.2) {
    phaseLabel = 'CLOUD DESCENT';
  }

  return {
    canopyOpacity: Number(canopyOpacity.toFixed(4)),
    shadowStrength: Number(shadowStrength.toFixed(4)),
    streetWetness: Number(streetWetness.toFixed(4)),
    phaseLabel
  };
}

let sharedDistanceImgPromise = null;
function loadIslandDistanceImage() {
  if (!sharedDistanceImgPromise) {
    sharedDistanceImgPromise = new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = (err) => {
        sharedDistanceImgPromise = null;
        reject(err);
      };
      img.src = distanceUrl;
    });
  }
  return sharedDistanceImgPromise;
}

const VERTEX_SHADER_SOURCE = `
  precision highp float;
  attribute vec2 a_pos;
  uniform mat4 u_matrix;
  varying highp vec2 v_local_meters;
  varying highp vec4 v_clip;

  void main() {
    v_local_meters = a_pos;
    vec4 clip = u_matrix * vec4(a_pos, 0.0, 1.0);
    v_clip = clip;
    gl_Position = clip;
  }
`;

const FRAGMENT_SHADER_SOURCE = `
  precision highp float;
  varying highp vec2 v_local_meters;
  varying highp vec4 v_clip;

  // Camera & World Uniforms (in exact Rotterdam local meters: +x = East, +y = South)
  uniform vec3 u_camera_meters;
  uniform float u_zoom;
  uniform float u_pitch_rad;
  uniform float u_bearing_rad;
  uniform float u_aspect;
  uniform float u_time;

  // Rotterdam Island Cutout Distance Field (for ground vs ocean surface shadow/shimmer weighting)
  uniform sampler2D u_distance_tex;
  uniform vec4 u_distance_bounds;
  uniform float u_max_distance;

  // 12-Node Spatial Weather Grid Texture & Local Meter Coordinates
  uniform sampler2D u_weather_tex;
  uniform vec2 u_node_meters[12];

  // Solar & Lightning Uniforms
  uniform vec3 u_sun_dir;
  uniform float u_sun_elevation_deg;
  uniform vec2 u_shadow_offset_meters;
  uniform float u_lightning_seed;

  // ---------------------------------------------------------------------------
  // Procedural Hash, Value Noise, 5-Octave FBM & Worley Cellular Billow Noise
  // ---------------------------------------------------------------------------
  float hash21(vec2 p) {
    p = fract(p * vec2(234.34, 435.345));
    p += dot(p, p + 34.23);
    return fract(p.x * p.y);
  }

  vec2 hash22(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
  }

  float valueNoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = hash21(i);
    float b = hash21(i + vec2(1.0, 0.0));
    float c = hash21(i + vec2(0.0, 1.0));
    float d = hash21(i + vec2(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
  }

  // Inverted cellular Worley noise for realistic cauliflower cumulus billows
  float worleyBillow(vec2 p) {
    vec2 n = floor(p);
    vec2 f = fract(p);
    float minDist = 1.0;
    for (int j = -1; j <= 1; j++) {
      for (int i = -1; i <= 1; i++) {
        vec2 neighbor = vec2(float(i), float(j));
        vec2 pt = hash22(n + neighbor);
        pt = 0.5 + 0.42 * sin(6.2831 * pt);
        vec2 diff = neighbor + pt - f;
        float d = dot(diff, diff);
        minDist = min(minDist, d);
      }
    }
    return 1.0 - sqrt(minDist);
  }

  float fbm5(vec2 p) {
    float val = 0.0;
    float amp = 0.52;
    mat2 rot = mat2(0.80, -0.60, 0.60, 0.80);
    for (int i = 0; i < 5; i++) {
      val += amp * valueNoise(p);
      p = rot * p * 2.03 + vec2(17.1, 31.7);
      amp *= 0.5;
    }
    return val;
  }

  // Performance: 4- and 3-octave FBM variants (clouds are rendered at reduced
  // resolution, so the 5th octave is sub-pixel and wasted work).
  float fbm4(vec2 p) {
    float val = 0.0;
    float amp = 0.54;
    mat2 rot = mat2(0.80, -0.60, 0.60, 0.80);
    for (int i = 0; i < 4; i++) {
      val += amp * valueNoise(p);
      p = rot * p * 2.03 + vec2(17.1, 31.7);
      amp *= 0.5;
    }
    return val;
  }

  float fbm3(vec2 p) {
    float val = 0.0;
    float amp = 0.57;
    mat2 rot = mat2(0.80, -0.60, 0.60, 0.80);
    for (int i = 0; i < 3; i++) {
      val += amp * valueNoise(p);
      p = rot * p * 2.03 + vec2(17.1, 31.7);
      amp *= 0.5;
    }
    return val;
  }

  // A continuous 3D density field. Volume samples share the same world-space
  // field so camera movement reveals the sides of the cloud, not stacked sprites.
  float hash31(vec3 p) {
    p = fract(p * 0.1031);
    p += dot(p, p.yzx + 33.33);
    return fract((p.x + p.y) * p.z);
  }

  float noise3(vec3 p) {
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(mix(hash31(i), hash31(i + vec3(1,0,0)), f.x),
          mix(hash31(i + vec3(0,1,0)), hash31(i + vec3(1,1,0)), f.x), f.y),
      mix(mix(hash31(i + vec3(0,0,1)), hash31(i + vec3(1,0,1)), f.x),
          mix(hash31(i + vec3(0,1,1)), hash31(i + vec3(1,1,1)), f.x), f.y), f.z);
  }

  float cloudVolume(vec3 p, float coverage, float highDeck) {
    if (coverage < 0.02 || p.z < 0.0 || p.z > 1.0) return 0.0;
    vec2 warp = vec2(valueNoise(p.xy * 0.35), valueNoise(p.xy * 0.35 + 19.7)) - 0.5;
    vec3 q = vec3(p.xy + warp * 1.3, p.z * 2.1);
    // Large weather patches contain smaller rounded lobes and ragged edges.
    float regional = fbm3(q.xy * 0.33 + vec2(7.2, 3.8));
    float shape = noise3(q * 1.5) * 0.57
                + noise3(q * 3.1 + 17.0) * 0.28
                + noise3(q * 6.4 + 31.0) * 0.15;
    float height = smoothstep(0.0, 0.18, p.z) * (1.0 - smoothstep(0.58, 1.0, p.z));
    float threshold = mix(0.78, 0.34, coverage);
    float body = shape * 0.68 + regional * 0.32 - threshold;
    float erosion = noise3(q * 13.0 + 8.0) * 0.055 + noise3(q * 26.0) * 0.025;
    return pow(max(0.0, body - erosion) * 5.0, 1.25) * height;
  }

  vec2 projectToAltitudeMeters(vec2 groundMeters, float H_meters);

  vec4 marchCloudDeck(vec2 groundMeters, vec2 driftKm, float coverage,
                     float baseHeight, float thickness, float highDeck) {
    vec3 accumulated = vec3(0.0);
    float transmission = 1.0;
    vec3 sunlight = normalize(vec3(u_sun_dir.x, -u_sun_dir.y, max(0.15, u_sun_dir.z)));
    float night = 1.0 - smoothstep(-6.0, 3.0, u_sun_elevation_deg);
    vec3 sunColor = mix(vec3(1.0, 0.985, 0.955), vec3(0.32, 0.38, 0.48), night);
    vec3 ambient = mix(vec3(0.67, 0.71, 0.77), vec3(0.16, 0.20, 0.28), night);
    for (int stepIndex = 0; stepIndex < 16; stepIndex++) {
      float z = 1.0 - (float(stepIndex) + 0.5) / 16.0;
      vec2 xy = projectToAltitudeMeters(groundMeters, baseHeight + z * thickness) * 0.001;
      vec3 p = vec3(xy * 1.10 + driftKm * 1.10 + vec2(highDeck * 23.1), z);
      float density = cloudVolume(p, coverage, highDeck);
      if (density > 0.002 && transmission > 0.015) {
        // Trace toward the sun through this same volume. This gives each lobe
        // a lit crown, shaded flank, and translucent edge without painted rims.
        float shadow = cloudVolume(p + sunlight * 0.16, coverage, highDeck) * 0.65
                     + cloudVolume(p + sunlight * 0.38, coverage, highDeck) * 0.35;
        float direct = exp(-shadow * 2.2);
        float powder = 1.0 - exp(-density * 2.0);
        vec3 light = mix(ambient, sunColor, direct * 0.82 + powder * 0.12);
        float alpha = 1.0 - exp(-density * mix(0.90, 0.72, highDeck));
        accumulated += transmission * alpha * light;
        transmission *= 1.0 - alpha;
      }
    }
    return vec4(accumulated, 1.0 - transmission);
  }

  // Sample Rotterdam Island signed/exterior distance field (0m on island land, up to 3200m in ocean)
  float sampleCoastDistanceMeters(vec2 localMeters) {
    vec2 distUv = (localMeters - u_distance_bounds.xy) / (u_distance_bounds.zw - u_distance_bounds.xy);
    if (distUv.x < 0.0 || distUv.x > 1.0 || distUv.y < 0.0 || distUv.y > 1.0) {
      return u_max_distance;
    }
    vec2 enc = texture2D(u_distance_tex, clamp(distUv, 0.0, 1.0)).rg;
    return dot(enc, vec2(65280.0, 255.0)) / 65535.0 * u_max_distance;
  }

  // GPU Spatial Interpolation across the 12 Rotterdam weather grid nodes (in local meters)
  void sampleSpatialWeather(
    vec2 localMeters,
    out vec4 outCloudsAndPrecip,
    out vec4 outWindStormFog
  ) {
    float weightSum = 0.0;
    vec4 acc0 = vec4(0.0);
    vec4 acc1 = vec4(0.0);

    for (int i = 0; i < 12; i++) {
      vec2 diffKm = (localMeters - u_node_meters[i]) * 0.001;
      float d2 = dot(diffKm, diffKm) + 3.2;
      float w = 1.0 / (d2 * sqrt(d2));

      float uCoord = (float(i) + 0.5) / 16.0;
      vec4 row0 = texture2D(u_weather_tex, vec2(uCoord, 0.25));
      vec4 row1 = texture2D(u_weather_tex, vec2(uCoord, 0.75));

      acc0 += row0 * w;
      acc1 += row1 * w;
      weightSum += w;
    }

    float invW = 1.0 / max(0.0001, weightSum);
    outCloudsAndPrecip = acc0 * invW;
    outWindStormFog = acc1 * invW;
  }

  // Project 3D camera-to-ground ray onto an elevated atmospheric plane at altitude H_meters
  vec2 projectToAltitudeMeters(vec2 groundMeters, float H_meters) {
    vec2 toCamXY = u_camera_meters.xy - groundMeters;
    float rayFrac = H_meters / max(H_meters + 450.0, u_camera_meters.z);
    vec2 parallaxOffset = clamp(toCamXY * rayFrac, vec2(-6500.0), vec2(6500.0));
    return groundMeters + parallaxOffset;
  }

  void main() {
    vec2 groundMeters = v_local_meters;
    vec2 ndc = v_clip.xy / max(0.0001, v_clip.w);

    // Soft outer-world horizon fade only at extreme distance (> 55 km from Rotterdam center)
    float distFromCityCenterKm = length(groundMeters) * 0.001;
    float worldHorizonFade = 1.0 - smoothstep(55.0, 95.0, distFromCityCenterKm);
    if (worldHorizonFade <= 0.002) {
      gl_FragColor = vec4(0.0);
      return;
    }

    // 1. Sample land vs ocean surface mask (used ONLY for ground surface interactions, NEVER to clip clouds!)
    float coastDist = sampleCoastDistanceMeters(groundMeters);
    float onIsland = 1.0 - smoothstep(0.0, 120.0, coastDist);

    // 2. Interpolate 12-node Rotterdam Spatial Weather Grid at cloud-deck position
    vec2 midCloudPosMeters = projectToAltitudeMeters(groundMeters, 1350.0);
    vec4 cloudsPrecip;
    vec4 windStormFog;
    sampleSpatialWeather(midCloudPosMeters, cloudsPrecip, windStormFog);

    float covLow = cloudsPrecip.r;
    float covMid = cloudsPrecip.g;
    float covHigh = cloudsPrecip.b;
    float precipMmH = cloudsPrecip.a * 16.0; // Decoded [0..16 mm/h]

    // Decode wind vector u (East m/s), v (North m/s) from [0..1] -> [-35..+35 m/s]
    vec2 windMs = (windStormFog.rg - 0.5) * 70.0;
    float stormIntensity = windStormFog.b;
    float fogDensity = windStormFog.a;

    // In localMeters: +x is East, +y is South (so Northward wind v > 0 moves toward -y).
    // Natural real-time wind advection: clouds glide smoothly and gently across Rotterdam
    // along the live KNMI wind vector at a believable, real-life pace.
    vec2 windAdvectKm = vec2(-windMs.x, windMs.y) * (u_time * 0.00026);

    // 3. Phase 4 Altitude Zoom-Fade ("Dive Through the Clouds" Mechanics)
    float baseAltitudeAlpha = (1.0 - smoothstep(12.0, 14.2, u_zoom));
    float radialDist = length(vec2(ndc.x * u_aspect, ndc.y));
    float descentProgress = smoothstep(11.9, 14.2, u_zoom);
    float radialParting = 1.0 - descentProgress * (1.0 - smoothstep(0.0, 1.05, radialDist)) * 0.68;
    float canopyZoomAlpha = max(0.025, baseAltitudeAlpha * radialParting * 0.92 + 0.025 * (1.0 - baseAltitudeAlpha));

    // Independent volumetric decks use the reported low/middle/high cover.
    vec2 physicalDriftKm = vec2(-windMs.x, windMs.y) * u_time * 0.001;
    float lowerCoverage = max(covLow, covMid);
    vec4 lowerCloud = marchCloudDeck(groundMeters, physicalDriftKm, lowerCoverage, 900.0, 1500.0, 0.0);
    vec4 upperCloud = marchCloudDeck(groundMeters, physicalDriftKm, covHigh, 3000.0, 650.0, 1.0);
    vec4 cloud = upperCloud + lowerCloud * (1.0 - upperCloud.a);
    float totalCloudDensity = cloud.a;
    vec3 cloudColor = cloud.rgb / max(0.001, cloud.a);
    float nightFactor = 1.0 - smoothstep(-8.0, 2.0, u_sun_elevation_deg);
    // Ground shadows remain broad and soft, anchored to the lower deck.
    vec2 shadowKm = (groundMeters + u_shadow_offset_meters) * 0.001;
    float shadowCloud = cloudVolume(vec3(shadowKm * 1.10 + physicalDriftKm * 1.10, 0.4), lowerCoverage, 0.0);
    float groundShadowAlpha = (1.0 - exp(-shadowCloud * 1.2)) * 0.25 * smoothstep(-2.0, 10.0, u_sun_elevation_deg);

    float goldenHourFactor = smoothstep(-2.0, 5.0, u_sun_elevation_deg) * (1.0 - smoothstep(6.0, 15.0, u_sun_elevation_deg));

    // 8. Coastal & Nieuwe Maas River Advection Fog
    vec2 groundKm = groundMeters * 0.001;
    float riverCenterYKm = 1.8 + 1.1 * sin(groundKm.x * 0.22) - groundKm.x * 0.08;
    float distToRiverKm = abs(groundKm.y - riverCenterYKm);
    float riverCorridorMask = exp(-distToRiverKm * distToRiverKm / 3.5);
    float coastalSeaMask = smoothstep(-8.0, -24.0, groundKm.x);
    float fogSpatialMask = clamp(max(riverCorridorMask * 0.9, coastalSeaMask * 0.85) + 0.35, 0.0, 1.0);

    float fogAlpha = 0.0;
    if (fogDensity > 0.01) {
      float fogNoise = fbm4(groundKm * 0.42 + windAdvectKm * 0.45 + vec2(4.2, 7.8));
      fogAlpha = fogDensity * fogSpatialMask * (0.45 + 0.55 * fogNoise) * (1.0 - smoothstep(11.2, 17.5, u_zoom)) * 0.52;
    }
    vec3 fogColor = mix(vec3(0.80, 0.86, 0.91), vec3(0.95, 0.82, 0.68), goldenHourFactor * 0.55);
    fogColor = mix(fogColor, vec3(0.22, 0.28, 0.38), nightFactor * 0.7);

    // 9. 3D Slanted Rain Streaks & Street-Level Wet Surface Shimmer
    float rainStrength = 0.0; // Observed rain is positioned by the radar layer.
    float rainStreakVal = 0.0;
    float wetShimmerVal = 0.0;

    if (rainStrength > 0.01) {
      float windTilt = clamp(windMs.x * 0.032, -0.48, 0.48);
      vec2 rainCoord1 = vec2(
        (ndc.x * u_aspect + ndc.y * windTilt) * 42.0 + groundKm.x * 1.8,
        ndc.y * 9.0 + u_time * (16.0 + precipMmH * 1.4)
      );
      vec2 rainCoord2 = vec2(
        (ndc.x * u_aspect + ndc.y * windTilt * 1.15) * 68.0 - groundKm.y * 1.8,
        ndc.y * 13.0 + u_time * (22.0 + precipMmH * 1.8) + 19.3
      );

      float s1 = smoothstep(0.76, 0.96, valueNoise(rainCoord1)) * valueNoise(rainCoord1 * vec2(0.15, 1.8));
      float s2 = smoothstep(0.79, 0.97, valueNoise(rainCoord2)) * valueNoise(rainCoord2 * vec2(0.15, 2.1));
      rainStreakVal = (s1 * 0.65 + s2 * 0.45) * rainStrength * (0.35 + 0.55 * totalCloudDensity);

      // Street-level wet road specular shimmer when zoomed in (zoom > 13.5) on Rotterdam Island
      float wetZoomFactor = smoothstep(13.5, 15.2, u_zoom);
      if (wetZoomFactor > 0.01 && onIsland > 0.1) {
        vec2 rippleUv = groundKm * 18.0 + vec2(u_time * 1.8, -u_time * 1.4);
        float ripple = smoothstep(0.72, 0.95, worleyBillow(rippleUv));
        wetShimmerVal = ripple * wetZoomFactor * rainStrength * onIsland * 0.22;
      }
    }

    // 10. Final Volumetric Compositing (Premultiplied Alpha across full sky & island)
    float finalCloudAlpha = totalCloudDensity * canopyZoomAlpha * worldHorizonFade;

    vec3 finalRgb = vec3(0.0);
    float finalAlpha = 0.0;

    // Layer A: Projected 3D ground cloud shadow on Rotterdam Island & coastal water
    float shadowContribution = groundShadowAlpha * (1.0 - finalCloudAlpha * 0.88) * worldHorizonFade;
    vec3 shadowColor = vec3(0.015, 0.035, 0.075);
    finalRgb = shadowColor * shadowContribution;
    finalAlpha = shadowContribution;

    // Layer B: Street-level wet specular shimmer + ground lightning illumination
    float groundFlash = wetShimmerVal;
    vec3 groundFlashRgb = vec3(0.72, 0.82, 0.96) * groundFlash * worldHorizonFade;
    finalRgb += groundFlashRgb * (1.0 - finalAlpha);
    finalAlpha = clamp(finalAlpha + groundFlash * 0.55 * worldHorizonFade, 0.0, 0.96);

    // Layer C: Coastal & Nieuwe Maas advection fog
    float effFogAlpha = fogAlpha * worldHorizonFade;
    finalRgb = finalRgb * (1.0 - effFogAlpha) + fogColor * effFogAlpha;
    finalAlpha = finalAlpha + effFogAlpha * (1.0 - finalAlpha);

    // Layer D: 3D Volumetric multi-deck clouds floating freely across island & ocean
    finalRgb = finalRgb * (1.0 - finalCloudAlpha) + cloudColor * finalCloudAlpha;
    finalAlpha = finalAlpha + finalCloudAlpha * (1.0 - finalAlpha);

    // Layer E: 3D slanted rain streaks
    float effRainAlpha = clamp(rainStreakVal * worldHorizonFade, 0.0, 0.55);
    vec3 rainStreakColor = mix(vec3(0.74, 0.83, 0.94), vec3(0.55, 0.68, 0.84), nightFactor * 0.5);
    finalRgb = finalRgb + rainStreakColor * effRainAlpha * (1.0 - finalAlpha * 0.35);
    finalAlpha = clamp(finalAlpha + effRainAlpha * (1.0 - finalAlpha), 0.0, 0.96);

    gl_FragColor = vec4(finalRgb, finalAlpha);
  }
`;

// ---------------------------------------------------------------------------
// Performance budget
// ---------------------------------------------------------------------------
// Clouds are soft, low-frequency phenomena, so the expensive volumetric shader is
// rendered into a reduced-resolution offscreen target and bilinearly upscaled onto the
// map. On a retina 2880x1800 canvas this cuts shaded pixels by 10x-20x.
const CLOUD_RENDER_MAX_SCALE = 0.5;           // never more than half the drawing-buffer res
const CLOUD_RENDER_MAX_LONG_SIDE = 920;       // crisp resolution when camera is stationary
const CLOUD_RENDER_MOVING_LONG_SIDE = 640;    // fast resolution during active pan/zoom/pitch
// Idle updates are requested at roughly 30Hz; actual frame rate is device-dependent.
const IDLE_FRAME_INTERVAL_MS = 33;

const COMPOSITE_VERTEX_SOURCE = `
  precision mediump float;
  attribute vec2 a_pos;
  varying vec2 v_uv;
  void main() {
    v_uv = a_pos * 0.5 + 0.5;
    gl_Position = vec4(a_pos, 0.0, 1.0);
  }
`;

const COMPOSITE_FRAGMENT_SOURCE = `
  precision mediump float;
  uniform sampler2D u_tex;
  varying vec2 v_uv;
  void main() {
    gl_FragColor = texture2D(u_tex, v_uv);
  }
`;

function compileShader(gl, type, source) {
  const s = gl.createShader(type);
  gl.shaderSource(s, source);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    const info = gl.getShaderInfoLog(s);
    gl.deleteShader(s);
    throw new Error(`Weather Engine GLSL compile error: ${info}`);
  }
  return s;
}

/**
 * Custom WebGL layer for the sampled Rotterdam cloud volumes.
 */
export class VolumetricWeatherLayer {
  id = WEATHER_LAYER_ID;
  type = 'custom';
  renderingMode = '2d';

  constructor(distanceImage, stateController) {
    this.distanceImage = distanceImage;
    this.stateController = stateController;
    this.program = null;
    this.quadBuffer = null;
    this.distanceTexture = null;
    this.weatherTexture = null;
    this.weatherTexBytes = new Uint8Array(16 * 2 * 4);
    this.nodeMetersFlat = new Float32Array(24);
    this.startTime = typeof performance !== 'undefined' ? performance.now() : Date.now();
    this.map = null;

    // Offscreen reduced-resolution cloud render target + composite pass
    this.fbo = null;
    this.fboTexture = null;
    this.fboWidth = 0;
    this.fboHeight = 0;
    this.compositeProgram = null;
    this.compositeBuffer = null;
    this.repaintTimer = null;
    this.lastFboRenderMs = -1000;
    this.lastCamKey = '';

    ROTTERDAM_WEATHER_NODES.forEach((n, idx) => {
      const [mx, my] = localPoint([n.lon, n.lat]);
      this.nodeMetersFlat[idx * 2] = mx;
      this.nodeMetersFlat[idx * 2 + 1] = my;
    });
  }

  onAdd(map, gl) {
    this.map = map;
    const vs = compileShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER_SOURCE);
    const fs = compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER_SOURCE);

    const prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    gl.deleteShader(vs);
    gl.deleteShader(fs);

    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      throw new Error(`Weather Engine link error: ${gl.getProgramInfoLog(prog)}`);
    }

    this.program = prog;
    this.aPosLoc = gl.getAttribLocation(prog, 'a_pos');

    const uniformNames = [
      'u_matrix',
      'u_camera_meters',
      'u_zoom',
      'u_pitch_rad',
      'u_bearing_rad',
      'u_aspect',
      'u_time',
      'u_distance_tex',
      'u_distance_bounds',
      'u_max_distance',
      'u_weather_tex',
      'u_node_meters',
      'u_sun_dir',
      'u_sun_elevation_deg',
      'u_shadow_offset_meters',
      'u_lightning_seed'
    ];
    this.uniforms = {};
    for (const name of uniformNames) {
      this.uniforms[name] = gl.getUniformLocation(prog, name);
    }

    // Composite (upsample) program: draws the low-res cloud buffer over the map
    const cvs = compileShader(gl, gl.VERTEX_SHADER, COMPOSITE_VERTEX_SOURCE);
    const cfs = compileShader(gl, gl.FRAGMENT_SHADER, COMPOSITE_FRAGMENT_SOURCE);
    const cprog = gl.createProgram();
    gl.attachShader(cprog, cvs);
    gl.attachShader(cprog, cfs);
    gl.linkProgram(cprog);
    gl.deleteShader(cvs);
    gl.deleteShader(cfs);
    if (!gl.getProgramParameter(cprog, gl.LINK_STATUS)) {
      throw new Error(`Weather Engine composite link error: ${gl.getProgramInfoLog(cprog)}`);
    }
    this.compositeProgram = cprog;
    this.compositePosLoc = gl.getAttribLocation(cprog, 'a_pos');
    this.compositeTexLoc = gl.getUniformLocation(cprog, 'u_tex');
    this.compositeBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.compositeBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);

    // World-space atmospheric & ground canvas spanning [-140km, +140km] around Rotterdam
    // so clouds float freely over both Rotterdam Island and the surrounding North Sea / ocean
    const EXTENT = 140000;
    this.quadBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([
        -EXTENT, -EXTENT,
         EXTENT, -EXTENT,
        -EXTENT,  EXTENT,
         EXTENT,  EXTENT
      ]),
      gl.STATIC_DRAW
    );

    // Texture 0: Rotterdam Island cutout distance field
    this.distanceTexture = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.distanceTexture);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, this.distanceImage);
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.BROWSER_DEFAULT_WEBGL);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    // Texture 1: 12-Node Spatial Weather Data Texture (16x2 RGBA)
    this.weatherTexture = gl.createTexture();
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.weatherTexture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    this._uploadWeatherTexture(gl);
  }

  _uploadWeatherTexture(gl) {
    const nodes = this.stateController.getActiveNodes();
    const bytes = this.weatherTexBytes;

    for (let i = 0; i < 12; i++) {
      const n = nodes[i] || ROTTERDAM_WEATHER_NODES[i];
      const lon = n.lon ?? ROTTERDAM_WEATHER_NODES[i].lon;
      const lat = n.lat ?? ROTTERDAM_WEATHER_NODES[i].lat;
      const [mx, my] = localPoint([lon, lat]);
      this.nodeMetersFlat[i * 2] = mx;
      this.nodeMetersFlat[i * 2 + 1] = my;

      // Row 0: [cloud_cover_low, cloud_cover_mid, cloud_cover_high, precipitation (0..16 mm/h)]
      const r0 = i * 4;
      bytes[r0] = Math.round(Math.max(0, Math.min(255, ((n.cloud_cover_low ?? 30) / 100) * 255)));
      bytes[r0 + 1] = Math.round(Math.max(0, Math.min(255, ((n.cloud_cover_mid ?? 20) / 100) * 255)));
      bytes[r0 + 2] = Math.round(Math.max(0, Math.min(255, ((n.cloud_cover_high ?? 10) / 100) * 255)));
      bytes[r0 + 3] = Math.round(Math.max(0, Math.min(255, ((n.precipitation ?? 0) / 16.0) * 255)));

      // Row 1: [wind_u (-35..+35 m/s), wind_v (-35..+35 m/s), storm_intensity (0..1), fog_density (0..1)]
      const r1 = (16 + i) * 4;
      const uNorm = Math.max(0, Math.min(1, ((n.wind_u ?? 3.0) + 35.0) / 70.0));
      const vNorm = Math.max(0, Math.min(1, ((n.wind_v ?? 2.0) + 35.0) / 70.0));
      bytes[r1] = Math.round(uNorm * 255);
      bytes[r1 + 1] = Math.round(vNorm * 255);
      bytes[r1 + 2] = Math.round(Math.max(0, Math.min(255, (n.storm_intensity ?? 0) * 255)));
      bytes[r1 + 3] = Math.round(Math.max(0, Math.min(255, (n.fog_density ?? 0) * 255)));
    }

    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.weatherTexture);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 16, 2, 0, gl.RGBA, gl.UNSIGNED_BYTE, bytes);
  }

  render(gl, matrix) {
    if (!this.program || !this.map || !this.stateController.isEnabled()) return;

    const wasDirty = this.stateController.consumeDirtyFlag();
    if (wasDirty) {
      this._uploadWeatherTexture(gl);
    }

    const canvas = this.map.getCanvas();
    const width = canvas?.width || 1440;
    const height = canvas?.height || 900;
    const aspect = width / Math.max(1, height);

    const center = this.map.getCenter();
    const zoom = this.map.getZoom();
    const pitchRad = (this.map.getPitch() * Math.PI) / 180;
    const bearingRad = (this.map.getBearing() * Math.PI) / 180;

    const nowMs = typeof performance !== 'undefined' ? performance.now() : Date.now();
    const isMoving = typeof this.map.isMoving === 'function' && this.map.isMoving();
    const camKey = `${center.lng.toFixed(5)}|${center.lat.toFixed(5)}|${zoom.toFixed(3)}|${pitchRad.toFixed(3)}|${bearingRad.toFixed(3)}|${width}x${height}`;
    const camChanged = camKey !== this.lastCamKey;

    const targetLongSide = isMoving ? CLOUD_RENDER_MOVING_LONG_SIDE : CLOUD_RENDER_MAX_LONG_SIDE;
    const scale = Math.min(CLOUD_RENDER_MAX_SCALE, targetLongSide / Math.max(width, height));
    const fboW = Math.max(64, Math.round(width * scale));
    const fboH = Math.max(64, Math.round(height * scale));
    const sizeChanged = fboW !== this.fboWidth || fboH !== this.fboHeight;

    // Preserve whatever framebuffer/viewport MapLibre expects us to draw into
    const prevFramebuffer = gl.getParameter(gl.FRAMEBUFFER_BINDING);
    const prevViewport = gl.getParameter(gl.VIEWPORT);

    const shouldBakeFbo =
      !this.fbo ||
      wasDirty ||
      camChanged ||
      sizeChanged ||
      nowMs - this.lastFboRenderMs >= IDLE_FRAME_INTERVAL_MS - 4;

    if (shouldBakeFbo) {
      this._ensureRenderTarget(gl, fboW, fboH);
      this.lastCamKey = camKey;
      this.lastFboRenderMs = nowMs;

      // Reconstruct 3D camera position in Rotterdam local meters (+x = East, +y = South, +z = Altitude)
      const [camTargetX, camTargetY] = localPoint([center.lng, center.lat]);
      const approxAltMeters = Math.max(220.0, (29500000.0 / Math.pow(2.0, zoom)) * Math.cos(pitchRad));
      const horizBackoffMeters = approxAltMeters * Math.tan(pitchRad);
      const camX = camTargetX - Math.sin(bearingRad) * horizBackoffMeters;
      const camY = camTargetY + Math.cos(bearingRad) * horizBackoffMeters;
      const camZ = approxAltMeters;

      const elapsedSec = (nowMs - this.startTime) * 0.001;

      const solar = this.stateController.getActiveSolar();
      const azRad = ((solar.azimuth_deg ?? 195) * Math.PI) / 180;
      const elDeg = solar.elevation_deg ?? 32;
      const elRad = (elDeg * Math.PI) / 180;
      const sunDir = [
        Math.cos(elRad) * Math.sin(azRad),
        Math.cos(elRad) * Math.cos(azRad),
        Math.sin(elRad)
      ];

      // Calculate physical ground shadow offset in meters for cloud base at H = 1250m
      const clampedElRad = Math.max((10.0 * Math.PI) / 180.0, Math.min((82.0 * Math.PI) / 180.0, Math.abs(elRad)));
      const cotEl = Math.min(2.6, 1.0 / Math.tan(clampedElRad));
      const shadowHeightMeters = 1250.0;
      const shadowOffsetX = shadowHeightMeters * cotEl * Math.sin(azRad);
      const shadowOffsetY = -shadowHeightMeters * cotEl * Math.cos(azRad);

      // --- Pass 1: render volumetric clouds into reduced-resolution offscreen buffer ---
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo);
      gl.viewport(0, 0, fboW, fboH);
      gl.disable(gl.SCISSOR_TEST);
      gl.disable(gl.STENCIL_TEST);
      gl.disable(gl.DEPTH_TEST);
      gl.disable(gl.CULL_FACE);
      gl.disable(gl.BLEND);
      gl.colorMask(true, true, true, true);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);

      gl.useProgram(this.program);

      gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuffer);
      gl.enableVertexAttribArray(this.aPosLoc);
      gl.vertexAttribPointer(this.aPosLoc, 2, gl.FLOAT, false, 0, 0);

      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this.distanceTexture);
      gl.uniform1i(this.uniforms.u_distance_tex, 0);

      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, this.weatherTexture);
      gl.uniform1i(this.uniforms.u_weather_tex, 1);

      gl.uniformMatrix4fv(this.uniforms.u_matrix, false, localMatrix(matrix));
      gl.uniform3f(this.uniforms.u_camera_meters, camX, camY, camZ);
      gl.uniform1f(this.uniforms.u_zoom, zoom);
      gl.uniform1f(this.uniforms.u_pitch_rad, pitchRad);
      gl.uniform1f(this.uniforms.u_bearing_rad, bearingRad);
      gl.uniform1f(this.uniforms.u_aspect, aspect);
      gl.uniform1f(this.uniforms.u_time, elapsedSec);

      gl.uniform4fv(this.uniforms.u_distance_bounds, ISLAND_DISTANCE_BOUNDS);
      gl.uniform1f(this.uniforms.u_max_distance, ISLAND_MAX_DISTANCE);

      gl.uniform2fv(this.uniforms.u_node_meters, this.nodeMetersFlat);
      gl.uniform3f(this.uniforms.u_sun_dir, sunDir[0], sunDir[1], sunDir[2]);
      gl.uniform1f(this.uniforms.u_sun_elevation_deg, elDeg);
      gl.uniform2f(this.uniforms.u_shadow_offset_meters, shadowOffsetX, shadowOffsetY);
      gl.uniform1f(this.uniforms.u_lightning_seed, 1.37);

      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }

    // --- Pass 2: bilinear upsample composite onto the map (premultiplied alpha) ---
    gl.bindFramebuffer(gl.FRAMEBUFFER, prevFramebuffer);
    gl.viewport(prevViewport[0], prevViewport[1], prevViewport[2], prevViewport[3]);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

    gl.useProgram(this.compositeProgram);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.compositeBuffer);
    gl.enableVertexAttribArray(this.compositePosLoc);
    gl.vertexAttribPointer(this.compositePosLoc, 2, gl.FLOAT, false, 0, 0);
    gl.activeTexture(gl.TEXTURE2);
    gl.bindTexture(gl.TEXTURE_2D, this.fboTexture);
    gl.uniform1i(this.compositeTexLoc, 2);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    gl.activeTexture(gl.TEXTURE0);

    // Always schedule the next ~30fps wind advection tick so clouds never stop moving
    // after a camera pan/zoom finishes.
    this._scheduleIdleFrame();
  }

  _ensureRenderTarget(gl, w, h) {
    if (this.fbo && this.fboWidth === w && this.fboHeight === h) return;
    if (!this.fboTexture) this.fboTexture = gl.createTexture();
    gl.activeTexture(gl.TEXTURE2);
    gl.bindTexture(gl.TEXTURE_2D, this.fboTexture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    if (!this.fbo) this.fbo = gl.createFramebuffer();
    const prev = gl.getParameter(gl.FRAMEBUFFER_BINDING);
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.fboTexture, 0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, prev);
    gl.activeTexture(gl.TEXTURE0);
    this.fboWidth = w;
    this.fboHeight = h;
  }

  _scheduleIdleFrame() {
    if (this.repaintTimer) return;
    this.repaintTimer = setTimeout(() => {
      this.repaintTimer = null;
      if (this.map && this.stateController.isEnabled()) this.map.triggerRepaint();
    }, IDLE_FRAME_INTERVAL_MS);
  }

  onRemove(map, gl) {
    if (this.repaintTimer) {
      clearTimeout(this.repaintTimer);
      this.repaintTimer = null;
    }
    if (this.quadBuffer && gl.isBuffer(this.quadBuffer)) gl.deleteBuffer(this.quadBuffer);
    if (this.compositeBuffer && gl.isBuffer(this.compositeBuffer)) gl.deleteBuffer(this.compositeBuffer);
    if (this.distanceTexture && gl.isTexture(this.distanceTexture)) gl.deleteTexture(this.distanceTexture);
    if (this.weatherTexture && gl.isTexture(this.weatherTexture)) gl.deleteTexture(this.weatherTexture);
    if (this.fboTexture && gl.isTexture(this.fboTexture)) gl.deleteTexture(this.fboTexture);
    if (this.fbo && gl.isFramebuffer(this.fbo)) gl.deleteFramebuffer(this.fbo);
    if (this.program && gl.isProgram(this.program)) gl.deleteProgram(this.program);
    if (this.compositeProgram && gl.isProgram(this.compositeProgram)) gl.deleteProgram(this.compositeProgram);
    this.map = null;
  }
}

/**
 * Reactive controller managing live API telemetry polling, simulator overrides,
 * and WebGL custom layer lifecycle.
 */
export function createWeatherEngineController(map, onStateChange = null) {
  let enabled = true;
  let dirty = true;
  let livePayload = null;
  let activeNodes = [];
  let activeSolar = {};
  let pollInterval = null;
  let removed = false;
  let fetching = false;
  let requestFailed = false;
  let radarAt = null;
  let radarFrame = null;
  let radarFetching = false;
  let installingRadar = false;
  let installedRadarUrl = null;

  function installRadar() {
    if (!map || removed || installingRadar || !map.getStyle()) return;
    installingRadar = true;
    try {
    const age = radarAt ? (Date.now() - Date.parse(radarAt)) / 1000 : Infinity;
    if (!radarFrame || age > 1200 || age < -300) {
      if (map.getLayer('live-rain-radar')) map.removeLayer('live-rain-radar');
      if (map.getSource('live-rain-radar')) map.removeSource('live-rain-radar');
      return;
    }
    const source = map.getSource('live-rain-radar');
    if (source && installedRadarUrl !== radarFrame.tile_url) source.setTiles([radarFrame.tile_url]);
    else if (!source) map.addSource('live-rain-radar', {
      type: 'raster', tiles: [radarFrame.tile_url], tileSize: 512, maxzoom: 7,
      attribution: 'Weather data by RainViewer'
    });
    installedRadarUrl = radarFrame.tile_url;
    if (!map.getLayer('live-rain-radar')) map.addLayer({
      id: 'live-rain-radar', type: 'raster', source: 'live-rain-radar',
      paint: { 'raster-opacity': 0.6, 'raster-fade-duration': 300 }
    });
    } catch (_) {
      // Retry on the next style event if the style is still loading.
    } finally { installingRadar = false; }
  }

  async function refreshRadar() {
    if (!map || removed || radarFetching) return;
    radarFetching = true;
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 15000);
    try {
      const response = await fetch(`${WEATHER_API_BASE_URL}/api/v1/weather/radar`, {
        cache: 'no-store', signal: abort.signal
      });
      if (!response.ok) throw new Error('Radar unavailable');
      const data = await response.json();
      const frame = data.latest_frame;
      if (!frame || !Number.isFinite(frame.time) || !frame.tile_url?.startsWith('https://tilecache.rainviewer.com/')) throw new Error('Invalid radar');
      if (removed) return;
      radarFrame = frame;
      radarAt = new Date(frame.time * 1000).toISOString();
    } catch (_) {
      // Retain the previous observed frame only within its freshness window.
    } finally {
      clearTimeout(timeout);
      radarFetching = false;
      if (!removed) {
        installRadar();
        notify();
      }
    }
  }

  // Allow disabling weather overlay in automated pixel-diff ocean cutout tests via ?weather=off
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);
    if (params.get('weather') === 'off') {
      enabled = false;
    }
  }

  function computeSummaryState() {
    const nodes = activeNodes;
    const centerNode = nodes.find(n => n.node_id === 7) || {};
    const timestamps = nodes.map(n => Date.parse(n.timestamp)).filter(Number.isFinite);
    const validAt = timestamps.length === 12 ? Math.min(...timestamps) : NaN;
    const ageSeconds = (Date.now() - validAt) / 1000;
    const status = !nodes.length ? 'unavailable'
      : requestFailed || livePayload?.data_status !== 'fresh' || !Number.isFinite(ageSeconds) || ageSeconds > 1800 || ageSeconds < -300 ? 'stale' : 'live';
    const zoom = map ? map.getZoom() : 11.5;
    const altitude = computeAltitudeCloudFade(zoom);
    return {
      status,
      radarAt: radarAt && Date.now() - Date.parse(radarAt) <= 1200000 ? radarAt : null,
      isLive: status === 'live',
      validAt: Number.isFinite(validAt) ? new Date(validAt).toISOString() : null,
      source: livePayload?.source || 'Open-Meteo / KNMI HARMONIE model',
      enabled,
      temperatureC: centerNode.temperature_2m ?? null,
      cloudCoverPct: centerNode.cloud_cover ?? null,
      precipitationMmH: centerNode.precipitation ?? null,
      windSpeedKmh: centerNode.wind_speed_10m ?? null,
      windGustsKmh: centerNode.wind_gusts_10m ?? null,
      windDirectionDeg: centerNode.wind_direction_10m ?? null,
      weatherDescription: centerNode.weather_description || 'Weather unavailable',
      solar: activeSolar,
      altitudePhase: altitude.phaseLabel,
      canopyOpacity: altitude.canopyOpacity,
      nodes
    };
  }

  function notify() {
    if (onStateChange) {
      onStateChange(computeSummaryState());
    }
  }

  async function fetchLiveWeatherGrid() {
    if (fetching || removed) return;
    fetching = true;
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 15000);
    try {
      const res = await fetch(`${WEATHER_API_BASE_URL}/api/v1/weather/live`, {
        headers: { Accept: 'application/json' }, cache: 'no-store', signal: abort.signal
      });
      if (!res.ok) throw new Error('Weather unavailable');
      const data = await res.json();
      const nodes = data.grid_nodes;
      const fields = ['temperature_2m', 'cloud_cover', 'cloud_cover_low', 'cloud_cover_mid',
        'cloud_cover_high', 'precipitation', 'wind_speed_10m', 'wind_direction_10m',
        'wind_gusts_10m', 'wind_u', 'wind_v', 'fog_density', 'storm_intensity', 'lat', 'lon'];
      if (!Array.isArray(nodes) || nodes.length !== 12 ||
          new Set(nodes.map(n => n.node_id)).size !== 12 ||
          nodes.some(n => !ROTTERDAM_WEATHER_NODES.some(c => c.node_id === n.node_id && c.lat === n.lat && c.lon === n.lon) ||
            fields.some(key => !Number.isFinite(n[key])) || !Number.isFinite(Date.parse(n.timestamp))) ||
          !Number.isFinite(data.solar?.azimuth_deg) || !Number.isFinite(data.solar?.elevation_deg) ||
          !['fresh', 'stale'].includes(data.data_status)) throw new Error('Invalid weather snapshot');
      if (removed) return;
      activeNodes = [...nodes].sort((a, b) => a.node_id - b.node_id);
      activeSolar = data.solar;
      livePayload = data;
      requestFailed = false;
      dirty = true;
    } catch (_) {
      requestFailed = true;
    } finally {
      clearTimeout(timeout);
      fetching = false;
      if (!removed) {
        if (map) map.triggerRepaint();
        notify();
      }
    }
  }

  function setEnabled(val) {
    enabled = Boolean(val);
    if (map) map.triggerRepaint();
    notify();
  }

  const stateApi = {
    getActiveNodes: () => activeNodes,
    getActiveSolar: () => activeSolar,
    isEnabled: () => enabled && activeNodes.length === 12 && computeSummaryState().status === 'live',
    consumeDirtyFlag: () => {
      const wasDirty = dirty;
      dirty = false;
      return wasDirty;
    },
    setEnabled,
    getState: computeSummaryState,
    refreshLive: async () => { await Promise.allSettled([fetchLiveWeatherGrid(), refreshRadar()]); }
  };

  function ensureTopmostWeatherLayer() {
    if (!map || !map.getStyle() || !map.getLayer(WEATHER_LAYER_ID)) return;
    const layers = map.getStyle().layers;
    if (layers && layers.length > 0 && layers[layers.length - 1].id !== WEATHER_LAYER_ID) {
      try {
        map.moveLayer(WEATHER_LAYER_ID);
      } catch (_) {}
    }
  }

  async function attachLayer() {
    if (removed || !map || !map.getStyle()) return;
    if (map.getLayer(WEATHER_LAYER_ID)) {
      ensureTopmostWeatherLayer();
      return;
    }
    try {
      const img = await loadIslandDistanceImage();
      if (removed || !map.getStyle()) return;
      if (!map.getLayer(WEATHER_LAYER_ID)) {
        map.addLayer(new VolumetricWeatherLayer(img, stateApi));
      }
      ensureTopmostWeatherLayer();
    } catch (err) {
      console.warn('[WeatherEngine] Could not attach WebGL weather layer:', err);
    }
  }

  // HUD only cares about the altitude phase/canopy opacity during zoom — coalesce to one
  // check per animation frame and skip Svelte updates when nothing visible changed.
  let zoomRafPending = false;
  let lastAltitudeKey = '';
  function onZoomThrottled() {
    if (zoomRafPending) return;
    zoomRafPending = true;
    requestAnimationFrame(() => {
      zoomRafPending = false;
      if (removed || !map) return;
      const alt = computeAltitudeCloudFade(map.getZoom());
      const key = `${alt.phaseLabel}|${Math.round(alt.canopyOpacity * 20)}`;
      if (key !== lastAltitudeKey) {
        lastAltitudeKey = key;
        notify();
      }
    });
  }

  if (map) {
    if (map.isStyleLoaded()) {
      attachLayer();
    }
    map.on('load', attachLayer);
    map.on('load', refreshRadar);
    map.on('styledata', attachLayer);
    map.on('styledata', installRadar);
    map.on('zoom', onZoomThrottled);
    map.once('remove', () => {
      removed = true;
      if (pollInterval) clearInterval(pollInterval);
      map.off('load', refreshRadar);
      map.off('load', attachLayer);
      map.off('styledata', attachLayer);
      map.off('styledata', installRadar);
      map.off('zoom', onZoomThrottled);
    });
  }

  fetchLiveWeatherGrid();
  refreshRadar();
  pollInterval = setInterval(() => { fetchLiveWeatherGrid(); refreshRadar(); }, 60000);
  notify();

  return stateApi;
}


