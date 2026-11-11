import { derived, writable } from 'svelte/store';
import { dutch } from './translations-nl.js';

const languageKey = 'rotterdam-live-language';

function savedLanguage() {
  if (typeof window === 'undefined') return 'en';
  try {
    return window.localStorage.getItem(languageKey) === 'nl' ? 'nl' : 'en';
  } catch {
    return 'en';
  }
}

export const language = writable(savedLanguage());

export function setLanguage(value) {
  const next = value === 'nl' ? 'nl' : 'en';
  language.set(next);
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(languageKey, next);
  } catch {
    // The current session can still switch languages when storage is blocked.
  }
}

export function languageLocale(value) {
  return value === 'nl' ? 'nl-NL' : 'en-GB';
}

export function translate(value, message, variables) {
  const text = value === 'nl' && Object.hasOwn(dutch, message) ? dutch[message] : message;
  if (!variables) return text;
  return text.replace(/\{(\w+)\}/g, (token, name) => variables[name] ?? token);
}

export const t = derived(language, value => (message, variables) => translate(value, message, variables));

// The spatial weather feed supplies WMO codes and Dutch descriptions.
const weatherConditions = {
  0: ['Clear', 'Onbewolkt'],
  1: ['Mainly clear', 'Overwegend helder'],
  2: ['Partly cloudy', 'Half bewolkt'],
  3: ['Overcast', 'Geheel bewolkt'],
  45: ['Fog', 'Mist'],
  48: ['Freezing fog', 'Aanvriezende mist'],
  51: ['Light drizzle', 'Lichte motregen'],
  53: ['Moderate drizzle', 'Matige motregen'],
  55: ['Heavy drizzle', 'Dichte motregen'],
  56: ['Light freezing drizzle', 'Lichte ijzel'],
  57: ['Heavy freezing drizzle', 'Zware ijzel'],
  61: ['Light rain', 'Lichte regen'],
  63: ['Moderate rain', 'Matige regen'],
  65: ['Heavy rain', 'Zware regen'],
  66: ['Light freezing rain', 'Lichte ijsregen'],
  67: ['Heavy freezing rain', 'Zware ijsregen'],
  71: ['Light snow', 'Lichte sneeuwval'],
  73: ['Moderate snow', 'Matige sneeuwval'],
  75: ['Heavy snow', 'Zware sneeuwval'],
  77: ['Snow grains', 'Korrelsneeuw'],
  80: ['Light rain showers', 'Lichte regenbui'],
  81: ['Moderate rain showers', 'Matige regenbui'],
  82: ['Heavy rain showers', 'Zware regenbui'],
  85: ['Snow showers', 'Sneeuwbui'],
  86: ['Heavy snow showers', 'Zware sneeuwbui'],
  95: ['Thunderstorm', 'Onweer'],
  96: ['Thunderstorm with hail', 'Onweer met hagel'],
  99: ['Heavy thunderstorm with hail', 'Zwaar onweer met hagel']
};

export function weatherCondition(value, code, description) {
  const names = (Number.isInteger(code) ? weatherConditions[code] : undefined)
    ?? Object.values(weatherConditions).find(pair => pair.includes(description));
  return names ? names[value === 'nl' ? 1 : 0] : translate(value, description || 'Weather unavailable');
}
