/**
 * 60FPS WebGL2 / GLSL Hyper-Realistic Volumetric Weather Engine for Rotterdam Island
 *
 * Features:
 * 1. 12-Node Rotterdam Spatial Weather Grid packed into a GPU data texture + uniform array
 *    with smooth Inverse Distance Weighting (IDW) across neighborhoods (Maasvlakte -> Nesselande).
 * 2. Multi-layered volumetric clouds (Low Cumulus/Stratocumulus, Mid Altostratus/Nimbostratus,
 *    High Cirrus) using domain-warped Fractional Brownian Motion (FBM) + Worley cellular billow noise.
 * 3. Dynamic storm coloring:
 *    - Dry Cumulus & Cirrus (#F8FAFC -> #CBD5E1) with Beer-Lambert absorption & Henyey-Greenstein silver lining
 *    - Rain-Bearing Nimbostratus (#475569 -> #1E293B) over active precipitation cells
 *    - Severe Storm & Thunder Anvils (#111827 -> #090D16) with procedural in-cloud sheet lightning pulses
 * 4. Projected 3D ground cloud shadows offset by live Rotterdam solar azimuth & elevation vector:
 *    (dx, dy) = H_cloud * cot(theta_sun) * (sin(phi_sun), cos(phi_sun)).
 * 5. Real-time wind advection, 3D slanted GPU rain streaks, street-level wet surface specular shimmer
 *    (zoom > 13.5), and coastal/river advection fog along the Nieuwe Maas & Maasvlakte basins.
 * 6. Altitude zoom-fade ("Dive Through the Clouds" camera parting & smoothstep(14.2, 12.0, zoom)).
 */

import { ORIGIN, WORLD_ORIGIN, METERS_PER_WORLD, mercator } from './oceanGeometry.js';

export const WEATHER_LAYER_ID = 'rotterdam-volumetric-weather';

const ISLAND_DISTANCE_BOUNDS = [
  -10898.04410184292,
  -10460.0233404718,
  10974.834178106921,
  10900.988901952896
];
const ISLAND_MAX_DISTANCE = 3200;
const distanceUrl = new URL('./ocean-distance.png', import.meta.url).href;

const DEFAULT_API_BASE = typeof window !== 'undefined'
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
 * Interactive Weather Simulator Presets for testing and verifying all visual regimes
 */
export const WEATHER_SIMULATOR_PRESETS = {
  live: {
    id: 'live',
    label: 'Live Now',
    subtitle: 'Live KNMI HARMONIE 2km Grid',
    isLive: true
  },
  scattered_cumulus: {
    id: 'scattered_cumulus',
    label: 'Scattered Cumulus',
    subtitle: 'Fair-weather billows & crisp ground shadows',
    isLive: false,
    solar: {
      azimuth_deg: 196.0,
      elevation_deg: 43.0,
      is_day: 1,
      daylight_phase: 'day',
      shadow_offset_factor: [0.296, 1.03]
    },
    buildNodes: () =>
      ROTTERDAM_WEATHER_NODES.map((n, i) => {
        const coastal = Math.max(0, 1 - (n.lon - 3.985) / 0.59);
        const speedKmh = 18.0 + coastal * 6.0;
        const speedMs = speedKmh / 3.6;
        const dirDeg = 245;
        const rad = (dirDeg * Math.PI) / 180;
        return {
          ...n,
          cloud_cover: 36 + (i % 3) * 6,
          cloud_cover_low: 34 + coastal * 10,
          cloud_cover_mid: 18,
          cloud_cover_high: 14,
          precipitation: 0.0,
          rain: 0.0,
          showers: 0.0,
          snowfall: 0.0,
          weather_code: 1,
          weather_description: 'Licht bewolkt',
          wind_speed_10m: Number(speedKmh.toFixed(1)),
          wind_speed_ms: Number(speedMs.toFixed(2)),
          wind_direction_10m: dirDeg,
          wind_gusts_10m: Number((speedKmh * 1.3).toFixed(1)),
          wind_u: Number((-speedMs * Math.sin(rad)).toFixed(3)),
          wind_v: Number((-speedMs * Math.cos(rad)).toFixed(3)),
          temperature_2m: Number((18.5 - coastal * 1.8).toFixed(1)),
          relative_humidity_2m: 64,
          visibility: 38000,
          surface_pressure: 1022.4,
          cape: 40,
          is_day: 1,
          storm_intensity: 0.0,
          fog_density: 0.0,
          lightning_active: false
        };
      })
  },
  coastal_squall: {
    id: 'coastal_squall',
    label: 'Maasvlakte Coastal Squall',
    subtitle: 'Fierce North Sea squall in west, dry inland east',
    isLive: false,
    solar: {
      azimuth_deg: 215.0,
      elevation_deg: 26.0,
      is_day: 1,
      daylight_phase: 'day',
      shadow_offset_factor: [1.17, 1.68]
    },
    buildNodes: () =>
      ROTTERDAM_WEATHER_NODES.map((n) => {
        // Strong coastal squall on nodes 1..5 (west of 4.42E), clearing toward Nesselande
        const westFactor = Math.max(0, Math.min(1, (4.46 - n.lon) / 0.42));
        const precip = Number((westFactor * westFactor * 6.4).toFixed(2));
        const speedKmh = 24.0 + westFactor * 36.0;
        const gustsKmh = speedKmh * (1.35 + westFactor * 0.25);
        const speedMs = speedKmh / 3.6;
        const dirDeg = Math.round(255 - westFactor * 18);
        const rad = (dirDeg * Math.PI) / 180;
        return {
          ...n,
          cloud_cover: Math.round(32 + westFactor * 68),
          cloud_cover_low: Math.round(25 + westFactor * 73),
          cloud_cover_mid: Math.round(20 + westFactor * 70),
          cloud_cover_high: Math.round(30 + westFactor * 50),
          precipitation: precip,
          rain: precip,
          showers: Number((precip * 0.5).toFixed(2)),
          snowfall: 0.0,
          weather_code: precip > 4.0 ? 82 : (precip > 0.3 ? 61 : 2),
          weather_description: precip > 4.0 ? 'Zware kustbui' : (precip > 0.3 ? 'Lichte regen' : 'Half bewolkt'),
          wind_speed_10m: Number(speedKmh.toFixed(1)),
          wind_speed_ms: Number(speedMs.toFixed(2)),
          wind_direction_10m: dirDeg,
          wind_gusts_10m: Number(gustsKmh.toFixed(1)),
          wind_u: Number((-speedMs * Math.sin(rad)).toFixed(3)),
          wind_v: Number((-speedMs * Math.cos(rad)).toFixed(3)),
          temperature_2m: Number((16.8 - westFactor * 3.6).toFixed(1)),
          relative_humidity_2m: Math.round(72 + westFactor * 24),
          visibility: Math.round(28000 - westFactor * 24500),
          surface_pressure: Number((1009.5 - westFactor * 4.5).toFixed(1)),
          cape: Math.round(80 + westFactor * 780),
          is_day: 1,
          storm_intensity: Number((westFactor * 0.85).toFixed(3)),
          fog_density: Number((westFactor * 0.35).toFixed(3)),
          lightning_active: westFactor > 0.72
        };
      })
  },
  heavy_rain: {
    id: 'heavy_rain',
    label: 'Heavy Rain Front',
    subtitle: 'Slate-blue Nimbostratus deck & slanted rain shafts',
    isLive: false,
    solar: {
      azimuth_deg: 205.0,
      elevation_deg: 22.0,
      is_day: 1,
      daylight_phase: 'day',
      shadow_offset_factor: [1.04, 2.24]
    },
    buildNodes: () =>
      ROTTERDAM_WEATHER_NODES.map((n, i) => {
        const precip = Number((2.4 + Math.sin(i * 0.7) * 1.1).toFixed(2));
        const speedKmh = 36.0 + (i % 4) * 2.5;
        const speedMs = speedKmh / 3.6;
        const dirDeg = 228;
        const rad = (dirDeg * Math.PI) / 180;
        return {
          ...n,
          cloud_cover: 96,
          cloud_cover_low: 92,
          cloud_cover_mid: 94,
          cloud_cover_high: 65,
          precipitation: precip,
          rain: precip,
          showers: 0.4,
          snowfall: 0.0,
          weather_code: 63,
          weather_description: 'Matige tot zware regen',
          wind_speed_10m: Number(speedKmh.toFixed(1)),
          wind_speed_ms: Number(speedMs.toFixed(2)),
          wind_direction_10m: dirDeg,
          wind_gusts_10m: Number((speedKmh * 1.45).toFixed(1)),
          wind_u: Number((-speedMs * Math.sin(rad)).toFixed(3)),
          wind_v: Number((-speedMs * Math.cos(rad)).toFixed(3)),
          temperature_2m: 13.4,
          relative_humidity_2m: 93,
          visibility: 4200,
          surface_pressure: 1004.2,
          cape: 220,
          is_day: 1,
          storm_intensity: 0.48,
          fog_density: 0.28,
          lightning_active: false
        };
      })
  },
  night_thunderstorm: {
    id: 'night_thunderstorm',
    label: 'Severe Night Thunderstorm',
    subtitle: 'Obsidian storm anvils & in-cloud sheet lightning',
    isLive: false,
    solar: {
      azimuth_deg: 340.0,
      elevation_deg: -18.0,
      is_day: 0,
      daylight_phase: 'night',
      shadow_offset_factor: [0.65, -1.8]
    },
    buildNodes: () =>
      ROTTERDAM_WEATHER_NODES.map((n, i) => {
        const cellBoost = Math.exp(-Math.pow((n.lon - 4.44) / 0.22, 2));
        const precip = Number((5.2 + cellBoost * 5.8).toFixed(2));
        const speedKmh = 54.0 + cellBoost * 22.0;
        const gustsKmh = 78.0 + cellBoost * 24.0;
        const speedMs = speedKmh / 3.6;
        const dirDeg = 240 + (i % 3) * 5;
        const rad = (dirDeg * Math.PI) / 180;
        return {
          ...n,
          cloud_cover: 100,
          cloud_cover_low: 98,
          cloud_cover_mid: 98,
          cloud_cover_high: 94,
          precipitation: precip,
          rain: precip * 0.7,
          showers: precip * 0.3,
          snowfall: 0.0,
          weather_code: 99,
          weather_description: 'Zwaar onweer met windstoten',
          wind_speed_10m: Number(speedKmh.toFixed(1)),
          wind_speed_ms: Number(speedMs.toFixed(2)),
          wind_direction_10m: dirDeg,
          wind_gusts_10m: Number(gustsKmh.toFixed(1)),
          wind_u: Number((-speedMs * Math.sin(rad)).toFixed(3)),
          wind_v: Number((-speedMs * Math.cos(rad)).toFixed(3)),
          temperature_2m: 14.2,
          relative_humidity_2m: 96,
          visibility: 2100,
          surface_pressure: 994.8,
          cape: Math.round(1350 + cellBoost * 650),
          is_day: 0,
          storm_intensity: Number(Math.min(1.0, 0.82 + cellBoost * 0.18).toFixed(3)),
          fog_density: 0.42,
          lightning_active: true
        };
      })
  },
  harbor_fog: {
    id: 'harbor_fog',
    label: 'Dense Harbor Fog',
    subtitle: 'Nieuwe Maas & Maasvlakte golden-hour advection mist',
    isLive: false,
    solar: {
      azimuth_deg: 118.0,
      elevation_deg: 6.5,
      is_day: 1,
      daylight_phase: 'golden_hour',
      shadow_offset_factor: [-3.1, 1.65]
    },
    buildNodes: () =>
      ROTTERDAM_WEATHER_NODES.map((n) => {
        const isWaterCorridor = n.zone === 'coastal' || n.zone === 'harbor' || n.zone === 'river';
        const speedKmh = isWaterCorridor ? 9.5 : 6.5;
        const speedMs = speedKmh / 3.6;
        const dirDeg = 105;
        const rad = (dirDeg * Math.PI) / 180;
        return {
          ...n,
          cloud_cover: isWaterCorridor ? 68 : 42,
          cloud_cover_low: isWaterCorridor ? 78 : 45,
          cloud_cover_mid: 15,
          cloud_cover_high: 22,
          precipitation: 0.0,
          rain: 0.0,
          showers: 0.0,
          snowfall: 0.0,
          weather_code: 45,
          weather_description: 'Dichte haven- en riviermist',
          wind_speed_10m: speedKmh,
          wind_speed_ms: Number(speedMs.toFixed(2)),
          wind_direction_10m: dirDeg,
          wind_gusts_10m: Number((speedKmh * 1.2).toFixed(1)),
          wind_u: Number((-speedMs * Math.sin(rad)).toFixed(3)),
          wind_v: Number((-speedMs * Math.cos(rad)).toFixed(3)),
          temperature_2m: 9.8,
          relative_humidity_2m: isWaterCorridor ? 99 : 94,
          visibility: isWaterCorridor ? 450 : 1400,
          surface_pressure: 1024.0,
          cape: 0,
          is_day: 1,
          storm_intensity: 0.0,
          fog_density: isWaterCorridor ? 0.96 : 0.68,
          lightning_active: false
        };
      })
  }
};

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
  const activeNodes = nodes?.length ? nodes : WEATHER_SIMULATOR_PRESETS.scattered_cumulus.buildNodes();
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
  varying highp vec2 v_ndc;
  varying highp vec2 v_uv;

  void main() {
    v_ndc = a_pos;
    v_uv = a_pos * 0.5 + 0.5;
    gl_Position = vec4(a_pos, 0.0, 1.0);
  }
`;

const FRAGMENT_SHADER_SOURCE = `
  precision highp float;
  varying highp vec2 v_ndc;
  varying highp vec2 v_uv;

  // Camera & World Reconstruction Uniforms
  uniform vec2 u_center_lnglat;
  uniform vec2 u_span_lnglat;
  uniform float u_zoom;
  uniform float u_pitch_rad;
  uniform float u_bearing_rad;
  uniform float u_aspect;
  uniform float u_time;

  // Rotterdam Island Cutout Distance Field
  uniform sampler2D u_distance_tex;
  uniform vec4 u_distance_bounds;
  uniform float u_max_distance;
  uniform vec2 u_world_origin;
  uniform float u_meters_per_world;

  // 12-Node Spatial Weather Grid Texture & Coordinates
  uniform sampler2D u_weather_tex;
  uniform vec2 u_node_coords[12];

  // Solar & Lightning Uniforms
  uniform vec3 u_sun_dir;
  uniform float u_sun_elevation_deg;
  uniform vec2 u_shadow_offset_deg;
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

  // Domain-warped FBM + Worley composite cloud density field
  float evaluateCloudDeck(vec2 worldUv, vec2 windAdvect, float coverage, float billowWeight) {
    if (coverage <= 0.01) return 0.0;
    vec2 p = worldUv + windAdvect;

    // Stage 1 domain warp
    vec2 q = vec2(
      fbm5(p + vec2(0.0, 0.0)),
      fbm5(p + vec2(5.2, 1.3))
    );

    // Stage 2 billow + FBM synthesis
    vec2 warped = p + 1.35 * q;
    float baseFbm = fbm5(warped * 1.4);
    float cellular = worleyBillow(warped * 2.3) * 0.65 + worleyBillow(warped * 4.8) * 0.35;
    float combined = mix(baseFbm, baseFbm * 0.62 + cellular * 0.38, billowWeight);

    // Shape cloud coverage threshold smoothly
    float thresh = mix(0.68, 0.16, clamp(coverage, 0.0, 1.0));
    float edge = mix(0.96, 0.72, clamp(coverage, 0.0, 1.0));
    return smoothstep(thresh, edge, combined);
  }

  // Henyey-Greenstein phase function for silver-lining forward scattering
  float henyeyGreenstein(float cosTheta, float g) {
    float g2 = g * g;
    float denom = max(0.001, pow(1.0 + g2 - 2.0 * g * cosTheta, 1.5));
    return (1.0 - g2) / (4.0 * 3.14159265 * denom);
  }

  // Sample Rotterdam Island signed/exterior distance field (meters outside boundary)
  float sampleCoastDistanceMeters(vec2 lngLat) {
    float mx = (lngLat.x + 180.0) / 360.0;
    float latRad = lngLat.y * 0.017453292519943295;
    float my = (1.0 - log(tan(latRad) + 1.0 / cos(latRad)) / 3.141592653589793) * 0.5;
    vec2 localMeters = (vec2(mx, my) - u_world_origin) * u_meters_per_world;
    vec2 distUv = (localMeters - u_distance_bounds.xy) / (u_distance_bounds.zw - u_distance_bounds.xy);
    if (distUv.x < 0.0 || distUv.x > 1.0 || distUv.y < 0.0 || distUv.y > 1.0) {
      return u_max_distance;
    }
    vec2 enc = texture2D(u_distance_tex, clamp(distUv, 0.0, 1.0)).rg;
    return dot(enc, vec2(65280.0, 255.0)) / 65535.0 * u_max_distance;
  }

  // GPU Spatial Interpolation across the 12 Rotterdam weather grid nodes
  void sampleSpatialWeather(
    vec2 lngLat,
    out vec4 outCloudsAndPrecip,
    out vec4 outWindStormFog
  ) {
    float weightSum = 0.0;
    vec4 acc0 = vec4(0.0);
    vec4 acc1 = vec4(0.0);

    for (int i = 0; i < 12; i++) {
      vec2 nodePos = u_node_coords[i];
      vec2 diff = vec2((lngLat.x - nodePos.x) * 0.6168, lngLat.y - nodePos.y);
      float d2 = dot(diff, diff) + 0.00022;
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

  void main() {
    // 1. Reconstruct ground world coordinates (lng, lat) with pitch & bearing awareness
    float pitchScale = 1.0 / max(0.38, 1.0 - v_ndc.y * sin(u_pitch_rad) * 0.55);
    vec2 screenOffset = vec2(v_ndc.x * pitchScale, v_ndc.y * pitchScale);

    float cosB = cos(u_bearing_rad);
    float sinB = sin(u_bearing_rad);
    vec2 rotOffset = vec2(
      screenOffset.x * cosB - screenOffset.y * sinB,
      screenOffset.x * sinB + screenOffset.y * cosB
    );

    vec2 groundLngLat = u_center_lnglat + rotOffset * u_span_lnglat * 0.5;

    // 2. Sample Rotterdam Island distance field (0m on island, up to 3200m in ocean)
    float coastDist = sampleCoastDistanceMeters(groundLngLat);
    float onIsland = 1.0 - smoothstep(0.0, 90.0, coastDist);
    float islandAtmosphereEnvelope = 1.0 - smoothstep(450.0, 3150.0, coastDist);

    if (islandAtmosphereEnvelope <= 0.002) {
      gl_FragColor = vec4(0.0);
      return;
    }

    // 3. Interpolate 12-node Rotterdam Spatial Weather Grid on GPU
    vec4 cloudsPrecip;
    vec4 windStormFog;
    sampleSpatialWeather(groundLngLat, cloudsPrecip, windStormFog);

    float covLow = cloudsPrecip.r;
    float covMid = cloudsPrecip.g;
    float covHigh = cloudsPrecip.b;
    float precipMmH = cloudsPrecip.a * 16.0; // Decoded [0..16 mm/h]

    // Decode wind vector u, v in m/s from [0..1] -> [-35..+35 m/s]
    vec2 windMs = (windStormFog.rg - 0.5) * 70.0;
    float stormIntensity = windStormFog.b;
    float fogDensity = windStormFog.a;

    // Convert wind (m/s) to continuous UV advection in Rotterdam local scale
    vec2 windUvVel = windMs * 0.0038;

    // 4. Phase 4 Altitude Zoom-Fade ("Dive Through the Clouds" Mechanics)
    float baseAltitudeAlpha = smoothstep(14.2, 12.0, u_zoom);
    float radialDist = length(vec2(v_ndc.x * u_aspect, v_ndc.y));
    float descentProgress = smoothstep(11.9, 14.2, u_zoom);
    float radialParting = 1.0 - descentProgress * (1.0 - smoothstep(0.0, 1.05, radialDist)) * 0.68;
    float canopyZoomAlpha = max(0.025, baseAltitudeAlpha * radialParting * 0.94 + 0.025 * (1.0 - baseAltitudeAlpha));

    // 5. 3D Parallax Coordinates for Low, Mid, and High Cloud Decks
    vec2 viewRayTilt = vec2(v_ndc.x * 0.0045 + sin(u_pitch_rad) * sinB * 0.012, v_ndc.y * 0.0045 + sin(u_pitch_rad) * cosB * 0.012);
    vec2 baseWorldUv = (groundLngLat - vec2(4.30, 51.90)) * vec2(16.0 * 0.6168, 16.0);

    vec2 uvLow = baseWorldUv + viewRayTilt * 0.85;
    vec2 uvMid = baseWorldUv * 0.72 + viewRayTilt * 1.65 + vec2(3.7, 8.1);
    vec2 uvHigh = baseWorldUv * 0.45 + viewRayTilt * 2.60 + vec2(11.4, 2.9);

    float dLow = evaluateCloudDeck(uvLow, -windUvVel * u_time * 1.0, covLow, 0.85);
    float dMid = evaluateCloudDeck(uvMid, -windUvVel * u_time * 1.35, covMid, 0.55);
    // High cirrus uses stretched anisotropic coordinates along wind direction
    float dHigh = evaluateCloudDeck(uvHigh * vec2(1.6, 0.75), -windUvVel * u_time * 1.85, covHigh, 0.15) * 0.55;

    float totalCloudDensity = clamp(dLow * 0.68 + dMid * 0.52 + dHigh * 0.32, 0.0, 1.0);

    // 6. Projected Ground Cloud Shadows on Rotterdam Island
    // Sample cloud density offset by live solar azimuth & elevation vector
    vec2 shadowSampleUv = baseWorldUv + u_shadow_offset_deg * 0.42;
    float shadowCloudLow = evaluateCloudDeck(shadowSampleUv, -windUvVel * u_time * 1.0, covLow, 0.80);
    float shadowCloudMid = evaluateCloudDeck(shadowSampleUv * 0.72 + vec2(3.7, 8.1), -windUvVel * u_time * 1.35, covMid, 0.50);
    float shadowDensity = clamp(shadowCloudLow * 0.75 + shadowCloudMid * 0.45, 0.0, 1.0);

    // Daylight factor for ground shadows (shadows fade out smoothly at night)
    float daylightShadowFactor = smoothstep(-2.0, 10.0, u_sun_elevation_deg);
    float zoomShadowMod = 0.25 + 0.75 * smoothstep(16.5, 11.8, u_zoom);
    // Shadow is strongest on exposed island ground where upper cloud doesn't fully occlude
    float groundShadowAlpha = shadowDensity * daylightShadowFactor * zoomShadowMod * mix(0.35, 1.0, onIsland) * 0.46;

    // 7. Dynamic Cloud Coloring, Beer-Lambert Absorption & Henyey-Greenstein Silver Lining
    //Compute height gradient & internal self-shadowing via offset density sample toward sun
    vec2 sunStepUv = normalize(u_sun_dir.xy + vec2(0.0001)) * 0.14;
    float densityTowardSun = evaluateCloudDeck(uvLow + sunStepUv, -windUvVel * u_time * 1.0, covLow, 0.85);
    float opticalThickness = totalCloudDensity * (1.15 + precipMmH * 0.28 + stormIntensity * 1.1);
    float beerLambert = exp(-opticalThickness * (1.25 + densityTowardSun * 1.4));

    vec3 viewDir = normalize(vec3(v_ndc.x * 0.4, v_ndc.y * 0.4, 1.0));
    float cosAngle = clamp(dot(viewDir, normalize(u_sun_dir)), -1.0, 1.0);
    float hgPhase = henyeyGreenstein(cosAngle, 0.62);
    float silverLining = clamp(beerLambert * (0.55 + hgPhase * 1.8) + pow(max(0.0, 1.0 - totalCloudDensity), 2.2) * 0.35, 0.0, 1.0);

    // Regime 1: Dry Cumulus & Cirrus (#F8FAFC -> #CBD5E1)
    vec3 dryLitColor = vec3(0.973, 0.980, 0.988);   // #F8FAFC
    vec3 dryBaseColor = vec3(0.796, 0.835, 0.882);  // #CBD5E1

    // Regime 2: Rain-Bearing Nimbostratus (0.1 < precip < 4.0 mm/h: #475569 -> #1E293B)
    vec3 rainLitColor = vec3(0.278, 0.333, 0.412);   // #475569
    vec3 rainBaseColor = vec3(0.118, 0.161, 0.231);  // #1E293B

    // Regime 3: Severe Storm & Thunder Cells (precip >= 4.0 or WMO storm: #111827 -> #090D16)
    vec3 stormLitColor = vec3(0.067, 0.094, 0.153);  // #111827
    vec3 stormBaseColor = vec3(0.035, 0.051, 0.086); // #090D16

    float rainBlend = smoothstep(0.08, 2.2, precipMmH);
    float stormBlend = clamp(max(smoothstep(3.5, 6.5, precipMmH), smoothstep(0.45, 0.85, stormIntensity)), 0.0, 1.0);

    vec3 cloudLit = mix(mix(dryLitColor, rainLitColor, rainBlend), stormLitColor, stormBlend);
    vec3 cloudDark = mix(mix(dryBaseColor, rainBaseColor, rainBlend), stormBaseColor, stormBlend);

    // Time-of-Day / Solar Elevation Lighting Tint
    float goldenHourFactor = smoothstep(-2.0, 5.0, u_sun_elevation_deg) * (1.0 - smoothstep(6.0, 15.0, u_sun_elevation_deg));
    float nightFactor = 1.0 - smoothstep(-8.0, 2.0, u_sun_elevation_deg);

    vec3 goldenTint = vec3(1.0, 0.76, 0.52);
    vec3 nightMoonTint = vec3(0.42, 0.50, 0.66);

    cloudLit = mix(cloudLit, cloudLit * goldenTint, goldenHourFactor * 0.65);
    cloudLit = mix(cloudLit, cloudLit * nightMoonTint, nightFactor * 0.72);
    cloudDark = mix(cloudDark, cloudDark * vec3(0.48, 0.54, 0.68), nightFactor * 0.68);

    float lightMix = clamp(beerLambert * 0.78 + silverLining * 0.32, 0.0, 1.0);
    vec3 cloudColor = mix(cloudDark, cloudLit, lightMix);

    // 8. Procedural In-Cloud Sheet Lightning (active in storm / thunder cells)
    float lightningPulse = 0.0;
    if (stormIntensity > 0.55) {
      float flashCycle = floor(u_time * 0.85 + u_lightning_seed);
      float cellPhase = fract(u_time * 0.85 + u_lightning_seed);
      vec2 flashCenter = vec2(
        4.15 + hash21(vec2(flashCycle, 1.7)) * 0.38,
        51.88 + hash21(vec2(flashCycle, 9.3)) * 0.08
      );
      float distToBolt = length((groundLngLat - flashCenter) * vec2(0.6168, 1.0));
      float spatialEnvelope = exp(-distToBolt * distToBolt / 0.014);

      // Realistic double-pulse exponential decay flash
      float pulse1 = exp(-cellPhase * 22.0) * step(0.02, cellPhase);
      float pulse2 = exp(-max(0.0, cellPhase - 0.14) * 28.0) * step(0.14, cellPhase) * 0.75;
      float triggerMask = step(0.32, hash21(vec2(flashCycle, 4.2)));
      lightningPulse = (pulse1 + pulse2) * spatialEnvelope * triggerMask * smoothstep(0.55, 0.85, stormIntensity);

      vec3 lightningColor = vec3(0.82, 0.88, 1.0);
      cloudColor = mix(cloudColor, lightningColor, clamp(lightningPulse * totalCloudDensity * 0.92, 0.0, 0.95));
    }

    // 9. Coastal & Nieuwe Maas River Advection Fog
    // Nieuwe Maas river corridor S-curve approximation across Rotterdam
    float riverCenterLat = 51.908 + 0.014 * sin((groundLngLat.x - 4.35) * 14.0) + (4.25 - groundLngLat.x) * 0.06;
    float distToRiver = abs(groundLngLat.y - riverCenterLat);
    float riverCorridorMask = exp(-distToRiver * distToRiver / 0.00085);
    float maasvlakteBasinMask = smoothstep(4.32, 3.98, groundLngLat.x);
    float fogSpatialMask = clamp(max(riverCorridorMask * 0.9, maasvlakteBasinMask * 0.85) + 0.35 * onIsland, 0.0, 1.0);

    float fogNoise = fbm5(baseWorldUv * 1.8 - windUvVel * u_time * 0.45 + vec2(4.2, 7.8));
    float fogAlpha = fogDensity * fogSpatialMask * (0.45 + 0.55 * fogNoise) * smoothstep(17.5, 11.2, u_zoom) * 0.58;
    vec3 fogColor = mix(vec3(0.78, 0.84, 0.89), vec3(0.95, 0.82, 0.68), goldenHourFactor * 0.55);
    fogColor = mix(fogColor, vec3(0.22, 0.28, 0.38), nightFactor * 0.7);

    // 10. 3D Slanted Rain Streaks & Street-Level Wet Surface Shimmer
    float rainStrength = smoothstep(0.10, 4.5, precipMmH);
    float rainStreakVal = 0.0;
    float wetShimmerVal = 0.0;

    if (rainStrength > 0.01) {
      // Wind-tilted screen-space + world-space rain streaks
      float windTilt = clamp(windMs.x * 0.032, -0.48, 0.48);
      vec2 rainCoord1 = vec2(
        (v_ndc.x * u_aspect + v_ndc.y * windTilt) * 42.0 + groundLngLat.x * 120.0,
        v_ndc.y * 9.0 + u_time * (16.0 + precipMmH * 1.4)
      );
      vec2 rainCoord2 = vec2(
        (v_ndc.x * u_aspect + v_ndc.y * windTilt * 1.15) * 68.0 - groundLngLat.y * 140.0,
        v_ndc.y * 13.0 + u_time * (22.0 + precipMmH * 1.8) + 19.3
      );

      float s1 = smoothstep(0.76, 0.96, valueNoise(rainCoord1)) * valueNoise(rainCoord1 * vec2(0.15, 1.8));
      float s2 = smoothstep(0.79, 0.97, valueNoise(rainCoord2)) * valueNoise(rainCoord2 * vec2(0.15, 2.1));
      rainStreakVal = (s1 * 0.65 + s2 * 0.45) * rainStrength * (0.42 + 0.35 * dLow);

      // When zoomed in (zoom > 13.5) in rainy areas, add subtle wet-road/water specular shimmer
      float wetZoomFactor = smoothstep(13.5, 15.2, u_zoom);
      if (wetZoomFactor > 0.01 && onIsland > 0.1) {
        vec2 rippleUv = baseWorldUv * 85.0 + vec2(u_time * 1.8, -u_time * 1.4);
        float ripple = smoothstep(0.72, 0.95, worleyBillow(rippleUv));
        wetShimmerVal = ripple * wetZoomFactor * rainStrength * onIsland * 0.22;
      }
    }

    // 11. Final Volumetric Compositing (Premultiplied Alpha for MapLibre GL Custom Layer)
    float finalCloudAlpha = totalCloudDensity * canopyZoomAlpha * islandAtmosphereEnvelope;

    // Combine ground shadow (darkening), fog mist, cloud deck, rain streaks, and lightning glow
    vec3 finalRgb = vec3(0.0);
    float finalAlpha = 0.0;

    // Layer A: Ground cloud shadow on Rotterdam Island
    float shadowContribution = groundShadowAlpha * (1.0 - finalCloudAlpha * 0.85) * islandAtmosphereEnvelope;
    vec3 shadowColor = vec3(0.02, 0.04, 0.08);
    finalRgb = shadowColor * shadowContribution;
    finalAlpha = shadowContribution;

    // Layer B: Street-level wet specular shimmer + ground lightning illumination
    float groundFlash = lightningPulse * onIsland * 0.18 + wetShimmerVal;
    vec3 groundFlashRgb = vec3(0.72, 0.82, 0.96) * groundFlash * islandAtmosphereEnvelope;
    finalRgb += groundFlashRgb * (1.0 - finalAlpha);
    finalAlpha = clamp(finalAlpha + groundFlash * 0.55 * islandAtmosphereEnvelope, 0.0, 0.96);

    // Layer C: Coastal & Nieuwe Maas advection fog
    float effFogAlpha = fogAlpha * islandAtmosphereEnvelope;
    finalRgb = finalRgb * (1.0 - effFogAlpha) + fogColor * effFogAlpha;
    finalAlpha = finalAlpha + effFogAlpha * (1.0 - finalAlpha);

    // Layer D: Volumetric multi-deck clouds
    finalRgb = finalRgb * (1.0 - finalCloudAlpha) + cloudColor * finalCloudAlpha;
    finalAlpha = finalAlpha + finalCloudAlpha * (1.0 - finalAlpha);

    // Layer E: 3D slanted rain streaks
    float effRainAlpha = clamp(rainStreakVal * islandAtmosphereEnvelope, 0.0, 0.55);
    vec3 rainStreakColor = mix(vec3(0.74, 0.83, 0.94), vec3(0.55, 0.68, 0.84), nightFactor * 0.5);
    finalRgb = finalRgb + rainStreakColor * effRainAlpha * (1.0 - finalAlpha * 0.35);
    finalAlpha = clamp(finalAlpha + effRainAlpha * (1.0 - finalAlpha), 0.0, 0.96);

    gl_FragColor = vec4(finalRgb, finalAlpha);
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
 * Custom WebGL Layer implementing the 60FPS Rotterdam Volumetric Weather Engine
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
    this.nodeCoordsFlat = new Float32Array(24);
    this.startTime = typeof performance !== 'undefined' ? performance.now() : Date.now();
    this.map = null;

    ROTTERDAM_WEATHER_NODES.forEach((n, idx) => {
      this.nodeCoordsFlat[idx * 2] = n.lon;
      this.nodeCoordsFlat[idx * 2 + 1] = n.lat;
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
      'u_center_lnglat',
      'u_span_lnglat',
      'u_zoom',
      'u_pitch_rad',
      'u_bearing_rad',
      'u_aspect',
      'u_time',
      'u_distance_tex',
      'u_distance_bounds',
      'u_max_distance',
      'u_world_origin',
      'u_meters_per_world',
      'u_weather_tex',
      'u_node_coords',
      'u_sun_dir',
      'u_sun_elevation_deg',
      'u_shadow_offset_deg',
      'u_lightning_seed'
    ];
    this.uniforms = {};
    for (const name of uniformNames) {
      this.uniforms[name] = gl.getUniformLocation(prog, name);
    }

    // Fullscreen NDC triangle strip quad
    this.quadBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
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
      this.nodeCoordsFlat[i * 2] = n.lon ?? ROTTERDAM_WEATHER_NODES[i].lon;
      this.nodeCoordsFlat[i * 2 + 1] = n.lat ?? ROTTERDAM_WEATHER_NODES[i].lat;

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

  render(gl) {
    if (!this.program || !this.map || !this.stateController.isEnabled()) return;

    if (this.stateController.consumeDirtyFlag()) {
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

    // Compute visible geographic span in degrees at current zoom & viewport dimensions
    const worldSizePx = 512 * Math.pow(2, zoom);
    const degPerPxLng = 360.0 / worldSizePx;
    const cosLat = Math.cos((center.lat * Math.PI) / 180);
    const degPerPxLat = degPerPxLng * cosLat;
    const cssWidth = canvas?.clientWidth || width;
    const cssHeight = canvas?.clientHeight || height;
    const spanLng = cssWidth * degPerPxLng;
    const spanLat = cssHeight * degPerPxLat;

    const nowMs = typeof performance !== 'undefined' ? performance.now() : Date.now();
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
    const shadowFactor = solar.shadow_offset_factor || [0.4, 0.8];

    gl.useProgram(this.program);
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.CULL_FACE);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuffer);
    gl.enableVertexAttribArray(this.aPosLoc);
    gl.vertexAttribPointer(this.aPosLoc, 2, gl.FLOAT, false, 0, 0);

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.distanceTexture);
    gl.uniform1i(this.uniforms.u_distance_tex, 0);

    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.weatherTexture);
    gl.uniform1i(this.uniforms.u_weather_tex, 1);

    gl.uniform2f(this.uniforms.u_center_lnglat, center.lng, center.lat);
    gl.uniform2f(this.uniforms.u_span_lnglat, spanLng, spanLat);
    gl.uniform1f(this.uniforms.u_zoom, zoom);
    gl.uniform1f(this.uniforms.u_pitch_rad, pitchRad);
    gl.uniform1f(this.uniforms.u_bearing_rad, bearingRad);
    gl.uniform1f(this.uniforms.u_aspect, aspect);
    gl.uniform1f(this.uniforms.u_time, elapsedSec);

    gl.uniform4fv(this.uniforms.u_distance_bounds, ISLAND_DISTANCE_BOUNDS);
    gl.uniform1f(this.uniforms.u_max_distance, ISLAND_MAX_DISTANCE);
    gl.uniform2f(this.uniforms.u_world_origin, WORLD_ORIGIN[0], WORLD_ORIGIN[1]);
    gl.uniform1f(this.uniforms.u_meters_per_world, METERS_PER_WORLD);

    gl.uniform2fv(this.uniforms.u_node_coords, this.nodeCoordsFlat);
    gl.uniform3f(this.uniforms.u_sun_dir, sunDir[0], sunDir[1], sunDir[2]);
    gl.uniform1f(this.uniforms.u_sun_elevation_deg, elDeg);
    gl.uniform2f(this.uniforms.u_shadow_offset_deg, shadowFactor[0], shadowFactor[1]);
    gl.uniform1f(this.uniforms.u_lightning_seed, 1.37);

    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    // Maintain smooth 60FPS continuous wind advection & storm animation
    this.map.triggerRepaint();
  }

  onRemove(map, gl) {
    if (this.quadBuffer && gl.isBuffer(this.quadBuffer)) gl.deleteBuffer(this.quadBuffer);
    if (this.distanceTexture && gl.isTexture(this.distanceTexture)) gl.deleteTexture(this.distanceTexture);
    if (this.weatherTexture && gl.isTexture(this.weatherTexture)) gl.deleteTexture(this.weatherTexture);
    if (this.program && gl.isProgram(this.program)) gl.deleteProgram(this.program);
  }
}

/**
 * Reactive controller managing live API telemetry polling, simulator overrides,
 * and WebGL custom layer lifecycle.
 */
export function createWeatherEngineController(map, onStateChange = null) {
  let activePresetId = 'live';
  let enabled = true;
  let dirty = true;
  let livePayload = null;
  let liveNodes = WEATHER_SIMULATOR_PRESETS.scattered_cumulus.buildNodes();
  let activeNodes = liveNodes;
  let activeSolar = WEATHER_SIMULATOR_PRESETS.scattered_cumulus.solar;
  let pollInterval = null;
  let removed = false;

  // Allow disabling weather overlay in automated pixel-diff ocean cutout tests via ?weather=off
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);
    if (params.get('weather') === 'off') {
      enabled = false;
    }
  }

  function computeSummaryState() {
    const nodes = activeNodes;
    const count = Math.max(1, nodes.length);
    const avgTemp = nodes.reduce((s, n) => s + (n.temperature_2m ?? 16), 0) / count;
    const avgCloud = nodes.reduce((s, n) => s + (n.cloud_cover ?? 40), 0) / count;
    const maxPrecip = Math.max(...nodes.map((n) => n.precipitation ?? 0));
    const avgPrecip = nodes.reduce((s, n) => s + (n.precipitation ?? 0), 0) / count;
    const avgWindKmh = nodes.reduce((s, n) => s + (n.wind_speed_10m ?? 16), 0) / count;
    const maxGustsKmh = Math.max(...nodes.map((n) => n.wind_gusts_10m ?? 22));
    const centerNode = nodes[6] || nodes[0] || {};
    const zoom = map ? map.getZoom() : 11.5;
    const altitude = computeAltitudeCloudFade(zoom);

    return {
      presetId: activePresetId,
      isLive: activePresetId === 'live',
      enabled,
      temperatureC: Number(avgTemp.toFixed(1)),
      cloudCoverPct: Math.round(avgCloud),
      precipitationMmH: Number(maxPrecip > 0.2 ? maxPrecip.toFixed(1) : avgPrecip.toFixed(1)),
      windSpeedKmh: Number(avgWindKmh.toFixed(1)),
      windGustsKmh: Number(maxGustsKmh.toFixed(1)),
      windDirectionDeg: centerNode.wind_direction_10m ?? 235,
      weatherDescription: centerNode.weather_description || 'Wisselend bewolkt',
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
    try {
      const res = await fetch(`${WEATHER_API_BASE_URL}/api/v1/weather/live`, {
        headers: { Accept: 'application/json' },
        cache: 'no-store'
      });
      if (!res.ok) return;
      const data = await res.json();
      livePayload = data;

      if (Array.isArray(data.grid_nodes) && data.grid_nodes.length === 12) {
        liveNodes = data.grid_nodes;
      } else if (Array.isArray(data.features) && data.features.length === 12) {
        liveNodes = data.features.map((f) => f.properties);
      }

      if (data.solar) {
        activeSolar = data.solar;
      }

      if (activePresetId === 'live') {
        activeNodes = liveNodes;
        dirty = true;
        if (map) map.triggerRepaint();
        notify();
      }
    } catch (_) {
      // Retain last valid or synthesized grid if offline
    }
  }

  function setPreset(presetId) {
    const preset = WEATHER_SIMULATOR_PRESETS[presetId];
    if (!preset) return;
    activePresetId = presetId;

    if (preset.isLive) {
      activeNodes = liveNodes;
      if (livePayload?.solar) {
        activeSolar = livePayload.solar;
      }
      fetchLiveWeatherGrid();
    } else {
      activeNodes = preset.buildNodes();
      activeSolar = preset.solar;
    }

    dirty = true;
    if (map) map.triggerRepaint();
    notify();
  }

  function setEnabled(val) {
    enabled = Boolean(val);
    if (map) map.triggerRepaint();
    notify();
  }

  const stateApi = {
    getActiveNodes: () => activeNodes,
    getActiveSolar: () => activeSolar,
    isEnabled: () => enabled,
    consumeDirtyFlag: () => {
      const wasDirty = dirty;
      dirty = false;
      return wasDirty;
    },
    setPreset,
    setEnabled,
    getState: computeSummaryState,
    refreshLive: fetchLiveWeatherGrid
  };

  async function attachLayer() {
    if (removed || !map || !map.getStyle()) return;
    if (map.getLayer(WEATHER_LAYER_ID)) return;
    try {
      const img = await loadIslandDistanceImage();
      if (removed || !map.getStyle() || map.getLayer(WEATHER_LAYER_ID)) return;
      map.addLayer(new VolumetricWeatherLayer(img, stateApi));
    } catch (err) {
      console.warn('[WeatherEngine] Could not attach WebGL weather layer:', err);
    }
  }

  if (map) {
    if (map.isStyleLoaded()) {
      attachLayer();
    }
    map.on('load', attachLayer);
    map.on('styledata', attachLayer);
    map.on('zoom', notify);
    map.once('remove', () => {
      removed = true;
      if (pollInterval) clearInterval(pollInterval);
      map.off('load', attachLayer);
      map.off('styledata', attachLayer);
      map.off('zoom', notify);
    });
  }

  fetchLiveWeatherGrid();
  pollInterval = setInterval(fetchLiveWeatherGrid, 60000);
  notify();

  return stateApi;
}

