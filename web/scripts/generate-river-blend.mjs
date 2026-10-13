import { readFileSync, writeFileSync } from 'node:fs';
import { buffer, difference, intersect, featureCollection } from '@turf/turf';

const read = path => JSON.parse(readFileSync(new URL(path, import.meta.url)));
const boundary = read('../src/lib/rotterdam_boundary.json');
const city = boundary.features?.[0] ?? boundary;
const water = read('../data/river-water.json');
// Keep the blend off banks, quays, and buildings despite small differences
// between satellite imagery and the vector water survey.
const safeWater = buffer(water, -0.008, { units: 'kilometers', steps: 16 });
const transitionMeters = 180;
const interior = buffer(city, -(transitionMeters + 30) / 1000, { units: 'kilometers', steps: 16 });
const strip = difference(featureCollection([city, interior]));
const blend = intersect(featureCollection([safeWater, strip]));
if (!blend) throw new Error('No river-mouth blend geometry found.');
blend.properties = { transitionMeters, bankInsetMeters: 8, source: water.properties.source };
writeFileSync(new URL('../src/lib/river-blend.json', import.meta.url), JSON.stringify(blend) + '\n');
console.log('Generated water-only, interior river-mouth blend.');
