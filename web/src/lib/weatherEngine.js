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

  // Sculpted Cumulus & Nimbostratus Density Slice with Worley Cauliflower Edge Erosion
  // Returns density in [0..1] for a given horizontal world position (in km) and vertical slice fraction [0..1]
  float evaluateVolumetricCloudSlice(vec2 posKm, vec2 windAdvectKm, float coverage, float heightFrac) {
    if (coverage <= 0.015) return 0.0;

    // Advect coordinate in km (+x = East, +y = South; windMs.y > 0 is Northward = -y)
    vec2 p = posKm * 0.26 + windAdvectKm;

    // Stage 1: Organic curl/domain warp for fluid atmospheric motion
    vec2 warp = vec2(
      fbm5(p * 0.75 + vec2(1.7, 9.2)),
      fbm5(p * 0.75 + vec2(8.3, 2.8))
    ) - 0.5;
    vec2 wPos = p + warp * 0.85;

    // Stage 2: Macro weather fronts & cloud clusters (leaves natural clear-sky gaps)
    float macroSystem = fbm5(wPos * 0.52 + vec2(3.1, 7.4));
    float mesoCluster = fbm5(wPos * 1.25 - warp * 0.45);
    float baseShape = macroSystem * 0.58 + mesoCluster * 0.42;

    // Stage 3: Multi-octave Worley cellular cauliflower billows
    float billowCoarse = worleyBillow(wPos * 2.15 + vec2(heightFrac * 0.35, -heightFrac * 0.25));
    float billowFine = worleyBillow(wPos * 4.70 - vec2(heightFrac * 0.50, heightFrac * 0.40));
    float cauliflower = billowCoarse * 0.64 + billowFine * 0.36;

    // Erode cloud perimeter with cellular billows so edges look like crisp cumulus puffs
    // rather than flat blurry Perlin fog
    float cov = clamp(coverage, 0.0, 1.0);
    float coverageThreshold = mix(0.66, 0.34, pow(cov, 0.85));
    // Higher slices taper inward to form 3D rounded cumulus domes & towering tops
    float verticalTaper = heightFrac * (1.0 - cov * 0.35) * 0.13;
    float rawEnvelope = smoothstep(coverageThreshold + verticalTaper, coverageThreshold + verticalTaper + 0.26, baseShape);

    // Carve cauliflower billow detail into the cloud body and perimeter
    float sculpted = rawEnvelope * (0.58 + 0.42 * cauliflower) - (1.0 - cauliflower) * 0.22 * (1.0 - rawEnvelope);
    return clamp(smoothstep(0.08, 0.78, sculpted), 0.0, 1.0);
  }

  // High-altitude sheared ice-crystal Cirrus streaks (H ~ 3100m)
  float evaluateCirrusDeck(vec2 posKm, vec2 windAdvectKm, float coverage) {
    if (coverage <= 0.02) return 0.0;
    vec2 p = posKm * vec2(0.18, 0.34) + windAdvectKm * 1.45 + vec2(14.2, 6.8);
    float warp = fbm5(p * 0.8);
    float streak = fbm5(vec2(p.x * 1.8 + warp * 1.4, p.y * 0.65 - warp * 0.6));
    float thresh = mix(0.68, 0.42, clamp(coverage, 0.0, 1.0));
    return smoothstep(thresh, thresh + 0.28, streak) * 0.48;
  }

  // Henyey-Greenstein phase function for silver-lining forward scattering
  float henyeyGreenstein(float cosTheta, float g) {
    float g2 = g * g;
    float denom = max(0.001, pow(1.0 + g2 - 2.0 * g * cosTheta, 1.5));
    return (1.0 - g2) / (4.0 * 3.14159265 * denom);
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

    // In localMeters: +x is East, +y is South (so Northward wind v > 0 moves toward -y)
    vec2 windAdvectKm = vec2(-windMs.x, windMs.y) * (u_time * 0.014);

    // 3. Phase 4 Altitude Zoom-Fade ("Dive Through the Clouds" Mechanics)
    float baseAltitudeAlpha = smoothstep(14.2, 12.0, u_zoom);
    float radialDist = length(vec2(ndc.x * u_aspect, ndc.y));
    float descentProgress = smoothstep(11.9, 14.2, u_zoom);
    float radialParting = 1.0 - descentProgress * (1.0 - smoothstep(0.0, 1.05, radialDist)) * 0.68;
    float canopyZoomAlpha = max(0.025, baseAltitudeAlpha * radialParting * 0.92 + 0.025 * (1.0 - baseAltitudeAlpha));

    // 4. 4-Slice 3D Volumetric Raymarch Through Cloud Altitudes (950m -> 2050m) + High Cirrus (3100m)
    float effectiveCumulusCov = clamp(max(covLow, covMid * 0.85), 0.0, 1.0);

    vec2 pSlice0Km = projectToAltitudeMeters(groundMeters, 950.0) * 0.001;
    vec2 pSlice1Km = projectToAltitudeMeters(groundMeters, 1300.0) * 0.001;
    vec2 pSlice2Km = projectToAltitudeMeters(groundMeters, 1680.0) * 0.001;
    vec2 pSlice3Km = projectToAltitudeMeters(groundMeters, 2080.0) * 0.001;
    vec2 pCirrusKm = projectToAltitudeMeters(groundMeters, 3100.0) * 0.001;

    float d0 = evaluateVolumetricCloudSlice(pSlice0Km, windAdvectKm, effectiveCumulusCov, 0.10);
    float d1 = evaluateVolumetricCloudSlice(pSlice1Km, windAdvectKm * 1.06, effectiveCumulusCov, 0.40);
    float d2 = evaluateVolumetricCloudSlice(pSlice2Km, windAdvectKm * 1.12, effectiveCumulusCov, 0.72);
    float d3 = evaluateVolumetricCloudSlice(pSlice3Km, windAdvectKm * 1.18, effectiveCumulusCov, 1.00);
    float dCirrus = evaluateCirrusDeck(pCirrusKm, windAdvectKm, covHigh);

    // Combine 3D slices into volumetric optical depth and weighted vertical height [0..1]
    float totalCloudDensity = clamp(1.0 - (1.0 - d0 * 0.45) * (1.0 - d1 * 0.62) * (1.0 - d2 * 0.58) * (1.0 - d3 * 0.48), 0.0, 1.0);
    totalCloudDensity = clamp(totalCloudDensity + dCirrus * (1.0 - totalCloudDensity * 0.7), 0.0, 1.0);

    float weightedHeight = clamp(
      (d0 * 0.12 + d1 * 0.38 + d2 * 0.74 + d3 * 1.05 + dCirrus * 0.95) /
      max(0.001, d0 + d1 + d2 + d3 + dCirrus),
      0.0,
      1.0
    );

    // 5. Projected 3D Ground Cloud Shadows on Rotterdam Island & Surrounding Coastal Waters
    // Trace from ground point (Z = 0m) toward the sun to the cloud base altitude (H = 1250m)
    vec2 shadowSampleKm = (groundMeters + u_shadow_offset_meters) * 0.001;
    float shadowCloud = evaluateVolumetricCloudSlice(shadowSampleKm, windAdvectKm * 1.03, effectiveCumulusCov, 0.32);
    float daylightShadowFactor = smoothstep(-2.0, 10.0, u_sun_elevation_deg);
    float zoomShadowMod = 0.28 + 0.72 * smoothstep(16.5, 11.6, u_zoom);
    // Cast crisp 3D shadows on Rotterdam Island land and slightly softer shadows on the ocean water
    float surfaceShadowReceptivity = mix(0.58, 1.0, onIsland);
    float groundShadowAlpha = shadowCloud * daylightShadowFactor * zoomShadowMod * surfaceShadowReceptivity * 0.50;

    // 6. Directional 3D Self-Shadowing, Beer-Lambert Absorption & Henyey-Greenstein Silver Lining
    // Step 450m horizontally toward the sun in localMeters (+x = East, -y = North)
    vec2 sunHorizDirKm = normalize(vec2(u_sun_dir.x, -u_sun_dir.y) + vec2(0.0001)) * 0.55;
    float densityTowardSun = evaluateVolumetricCloudSlice(
      pSlice2Km + sunHorizDirKm,
      windAdvectKm * 1.10,
      effectiveCumulusCov,
      0.65
    );

    float rainDarkening = clamp(precipMmH * 0.16 + stormIntensity * 0.75, 0.0, 1.4);
    float opticalDepthTowardSun = densityTowardSun * (1.35 + rainDarkening) + (1.0 - weightedHeight) * 0.85;
    float beerLambert = exp(-opticalDepthTowardSun);

    vec3 viewDir = normalize(vec3(ndc.x * 0.45, ndc.y * 0.45, 1.0));
    float cosAngle = clamp(dot(viewDir, normalize(u_sun_dir)), -1.0, 1.0);
    float hgPhase = henyeyGreenstein(cosAngle, 0.65);

    // Bright rim scattering on wispy cumulus edges and sunlit tops
    float edgeTranslucency = totalCloudDensity * (1.0 - totalCloudDensity * 0.68) * 2.4;
    float silverLining = clamp(beerLambert * (0.45 + hgPhase * 1.6) + edgeTranslucency * 0.42 + weightedHeight * 0.35, 0.0, 1.0);

    // Regime 1: Dry Cumulus & Cirrus (#FFFFFF / #F8FAFC sunlit tops -> #CBD5E1 / #94A3B8 shadowed bases)
    vec3 dryLitColor = vec3(0.985, 0.992, 1.000);   // Crisp sunlit cumulus white
    vec3 dryBaseColor = vec3(0.710, 0.765, 0.835);  // Sculpted silver-slate cumulus underside

    // Regime 2: Rain-Bearing Nimbostratus (0.1 < precip < 4.0 mm/h: #64748B -> #1E293B)
    vec3 rainLitColor = vec3(0.380, 0.445, 0.535);
    vec3 rainBaseColor = vec3(0.118, 0.161, 0.231);

    // Regime 3: Severe Storm & Thunder Cells (precip >= 4.0 or WMO storm: #1E293B -> #090D16)
    vec3 stormLitColor = vec3(0.145, 0.190, 0.265);
    vec3 stormBaseColor = vec3(0.035, 0.051, 0.086);

    float rainBlend = smoothstep(0.10, 2.5, precipMmH);
    float stormBlend = clamp(max(smoothstep(3.5, 6.5, precipMmH), smoothstep(0.45, 0.85, stormIntensity)), 0.0, 1.0);

    vec3 cloudLit = mix(mix(dryLitColor, rainLitColor, rainBlend), stormLitColor, stormBlend);
    vec3 cloudDark = mix(mix(dryBaseColor, rainBaseColor, rainBlend), stormBaseColor, stormBlend);

    // Time-of-Day / Solar Elevation Lighting Tint
    float goldenHourFactor = smoothstep(-2.0, 5.0, u_sun_elevation_deg) * (1.0 - smoothstep(6.0, 15.0, u_sun_elevation_deg));
    float nightFactor = 1.0 - smoothstep(-8.0, 2.0, u_sun_elevation_deg);

    vec3 goldenTint = vec3(1.0, 0.78, 0.55);
    vec3 nightMoonTint = vec3(0.45, 0.54, 0.70);

    cloudLit = mix(cloudLit, cloudLit * goldenTint, goldenHourFactor * 0.65);
    cloudLit = mix(cloudLit, cloudLit * nightMoonTint, nightFactor * 0.70);
    cloudDark = mix(cloudDark, cloudDark * vec3(0.48, 0.54, 0.68), nightFactor * 0.68);

    float lightMix = clamp(beerLambert * 0.62 + silverLining * 0.48, 0.0, 1.0);
    vec3 cloudColor = mix(cloudDark, cloudLit, lightMix);

    // 7. Procedural In-Cloud Sheet Lightning (active in storm / thunder cells)
    float lightningPulse = 0.0;
    if (stormIntensity > 0.55) {
      float flashCycle = floor(u_time * 0.85 + u_lightning_seed);
      float cellPhase = fract(u_time * 0.85 + u_lightning_seed);
      vec2 flashCenterKm = vec2(
        -18.0 + hash21(vec2(flashCycle, 1.7)) * 28.0,
        -6.0 + hash21(vec2(flashCycle, 9.3)) * 12.0
      );
      float distToBoltKm = length(pSlice1Km - flashCenterKm);
      float spatialEnvelope = exp(-distToBoltKm * distToBoltKm / 42.0);

      // Realistic double-pulse exponential decay flash
      float pulse1 = exp(-cellPhase * 22.0) * step(0.02, cellPhase);
      float pulse2 = exp(-max(0.0, cellPhase - 0.14) * 28.0) * step(0.14, cellPhase) * 0.75;
      float triggerMask = step(0.32, hash21(vec2(flashCycle, 4.2)));
      lightningPulse = (pulse1 + pulse2) * spatialEnvelope * triggerMask * smoothstep(0.55, 0.85, stormIntensity);

      vec3 lightningColor = vec3(0.84, 0.90, 1.0);
      cloudColor = mix(cloudColor, lightningColor, clamp(lightningPulse * totalCloudDensity * 0.92, 0.0, 0.95));
    }

    // 8. Coastal & Nieuwe Maas River Advection Fog
    vec2 groundKm = groundMeters * 0.001;
    float riverCenterYKm = 1.8 + 1.1 * sin(groundKm.x * 0.22) - groundKm.x * 0.08;
    float distToRiverKm = abs(groundKm.y - riverCenterYKm);
    float riverCorridorMask = exp(-distToRiverKm * distToRiverKm / 3.5);
    float coastalSeaMask = smoothstep(-8.0, -24.0, groundKm.x);
    float fogSpatialMask = clamp(max(riverCorridorMask * 0.9, coastalSeaMask * 0.85) + 0.35, 0.0, 1.0);

    float fogNoise = fbm5(groundKm * 0.42 + windAdvectKm * 0.45 + vec2(4.2, 7.8));
    float fogAlpha = fogDensity * fogSpatialMask * (0.45 + 0.55 * fogNoise) * smoothstep(17.5, 11.2, u_zoom) * 0.52;
    vec3 fogColor = mix(vec3(0.80, 0.86, 0.91), vec3(0.95, 0.82, 0.68), goldenHourFactor * 0.55);
    fogColor = mix(fogColor, vec3(0.22, 0.28, 0.38), nightFactor * 0.7);

    // 9. 3D Slanted Rain Streaks & Street-Level Wet Surface Shimmer
    float rainStrength = smoothstep(0.10, 4.5, precipMmH);
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
    float groundFlash = lightningPulse * 0.18 + wetShimmerVal;
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
    this.nodeMetersFlat = new Float32Array(24);
    this.startTime = typeof performance !== 'undefined' ? performance.now() : Date.now();
    this.map = null;

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

    // Reconstruct 3D camera position in Rotterdam local meters (+x = East, +y = South, +z = Altitude)
    const [camTargetX, camTargetY] = localPoint([center.lng, center.lat]);
    const approxAltMeters = Math.max(220.0, (29500000.0 / Math.pow(2.0, zoom)) * Math.cos(pitchRad));
    const horizBackoffMeters = approxAltMeters * Math.tan(pitchRad);
    const camX = camTargetX - Math.sin(bearingRad) * horizBackoffMeters;
    const camY = camTargetY + Math.cos(bearingRad) * horizBackoffMeters;
    const camZ = approxAltMeters;

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

    // Calculate physical ground shadow offset in meters for cloud base at H = 1250m
    // In localMeters: +x = East (sin(az)), +y = South (-cos(az))
    const clampedElRad = Math.max((10.0 * Math.PI) / 180.0, Math.min((82.0 * Math.PI) / 180.0, Math.abs(elRad)));
    const cotEl = Math.min(2.6, 1.0 / Math.tan(clampedElRad));
    const shadowHeightMeters = 1250.0;
    const shadowOffsetX = shadowHeightMeters * cotEl * Math.sin(azRad);
    const shadowOffsetY = -shadowHeightMeters * cotEl * Math.cos(azRad);

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


