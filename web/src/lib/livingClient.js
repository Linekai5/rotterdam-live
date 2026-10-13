/**
 * Rotterdam Live — /living Domain Client & Types (Svelte + MapLibre GL)
 * 
 * Provides typed access to:
 * - Demographics: /api/v1/living/demographics
 * - Demographics Overview: /api/v1/living/demographics/overview
 * - Housing Analytics: /api/v1/living/housing
 * - Unified District Passport: /api/v1/living/districts/{name}/passport
 */

import { API_BASE_URL } from './liveLayers.js';

/**
 * @typedef {Object} AgeBrackets
 * @property {number|null} [0-14]
 * @property {number|null} [15-24]
 * @property {number|null} [25-44]
 * @property {number|null} [45-64]
 * @property {number|null} [65+]
 */

/**
 * @typedef {Object} DistrictDemographics
 * @property {string} district_code
 * @property {string} district_name
 * @property {number|null} total_population
 * @property {number|null} population_density_km2
 * @property {number|null} men
 * @property {number|null} women
 * @property {AgeBrackets} age_brackets
 * @property {number|null} total_households
 * @property {number|null} single_person_households
 * @property {number|null} single_person_pct
 * @property {number|null} average_household_size
 * @property {number|null} average_income_per_inhabitant
 * @property {string} source
 * @property {number} data_year
 * @property {string|null} updated_at
 */

/**
 * @typedef {Object} ConstructionEras
 * @property {{count: number, pct: number}} pre_war
 * @property {{count: number, pct: number}} post_war_reconstruction
 * @property {{count: number, pct: number}} late_20th_century
 * @property {{count: number, pct: number}} modern
 */

/**
 * @typedef {Object} DistrictHousing
 * @property {string} district_code
 * @property {string} district_name
 * @property {number} total_residential_units
 * @property {{average_m2: number|null, median_m2: number|null, min_m2: number|null, max_m2: number|null}} surface_area
 * @property {ConstructionEras} construction_eras
 * @property {number|null} average_woz_value
 * @property {{owner_occupied_pct: number|null, social_rent_pct: number|null, private_rent_pct: number|null}} tenure_breakdown
 * @property {{overall_index: number|null, safety_index: number|null, physical_index: number|null, social_index: number|null}} livability
 * @property {Record<string, number>} amenity_counts
 */

/**
 * @typedef {Object} DistrictPassport
 * @property {string} type - "Feature"
 * @property {string} id - District code (e.g. "WK059901")
 * @property {{type: string, coordinates: any}} geometry - MultiPolygon
 * @property {{
 *   district_code: string,
 *   district_name: string,
 *   demographics: DistrictDemographics,
 *   housing: DistrictHousing,
 *   amenities: Record<string, number>,
 *   livability: {overall_index: number|null, safety_index: number|null, physical_index: number|null, social_index: number|null},
 *   updated_at: string|null
 * }} properties
 */

/**
 * Fetch all district demographics or filter by district.
 * @param {string} [district]
 * @returns {Promise<{total_districts: number, data_year: number, source: string, districts: DistrictDemographics[]}|null>}
 */
export async function fetchDistrictDemographics(district = null) {
  try {
    const q = district ? `?district=${encodeURIComponent(district)}` : '';
    const res = await fetch(`${API_BASE_URL}/api/v1/living/demographics${q}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('[Living] Failed to fetch demographics:', err);
    return null;
  }
}

/**
 * Fetch high-level municipal demographic overview.
 * @returns {Promise<any|null>}
 */
export async function fetchDemographicsOverview() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/living/demographics/overview`);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('[Living] Failed to fetch demographics overview:', err);
    return null;
  }
}

/**
 * Fetch housing analytics and era distributions.
 * @param {string} [district]
 * @returns {Promise<any|null>}
 */
export async function fetchDistrictHousing(district = null) {
  try {
    const q = district ? `?district=${encodeURIComponent(district)}` : '';
    const res = await fetch(`${API_BASE_URL}/api/v1/living/housing${q}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('[Living] Failed to fetch housing metrics:', err);
    return null;
  }
}

/**
 * Fetch the Unified District Passport GeoJSON Feature for a specified district.
 * @param {string} districtName - e.g. "Centrum", "Feijenoord", "WK059901"
 * @returns {Promise<DistrictPassport|null>}
 */
export async function fetchDistrictPassport(districtName) {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/living/districts/${encodeURIComponent(districtName)}/passport`);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error(`[Living] Failed to fetch passport for ${districtName}:`, err);
    return null;
  }
}

/**
 * Render or highlight a District Passport polygon boundary in MapLibre GL.
 * @param {any} map - MapLibre GL map instance
 * @param {DistrictPassport} passport - GeoJSON Feature
 */
export function displayDistrictPassportLayer(map, passport) {
  if (!map || !passport) return;

  const sourceId = 'district-passport-source';
  const fillLayerId = 'district-passport-fill';
  const lineLayerId = 'district-passport-line';

  if (map.getSource(sourceId)) {
    map.getSource(sourceId).setData(passport);
  } else {
    map.addSource(sourceId, {
      type: 'geojson',
      data: passport
    });

    map.addLayer({
      id: fillLayerId,
      type: 'fill',
      source: sourceId,
      paint: {
        'fill-color': '#0ea5e9',
        'fill-opacity': 0.18
      }
    });

    map.addLayer({
      id: lineLayerId,
      type: 'line',
      source: sourceId,
      paint: {
        'line-color': '#38bdf8',
        'line-width': 2.5,
        'line-dasharray': [2, 1]
      }
    });
  }
}
