import { test, expect } from '@playwright/test';
import { PNG } from 'pngjs';
import { readFileSync } from 'node:fs';
import { booleanPointInPolygon, point } from '@turf/turf';
import { boundaryRing, localPoint } from '../../src/lib/oceanGeometry.js';

const boundary = JSON.parse(readFileSync(new URL('../../src/lib/rotterdam_boundary.json', import.meta.url)));
const city = boundary.features?.[0] ?? boundary;
const ring = boundaryRing(boundary);
const palette = JSON.parse(readFileSync(new URL('../../src/lib/ocean-palette.json', import.meta.url)));
const raster = new PNG({ width: 256, height: 256 });
for (let i = 0; i < raster.data.length; i += 4) raster.data.set([210,70,180,255], i);
const fixture = PNG.sync.write(raster);
function distance(p) {
  let best = Infinity;
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i], b = ring[(i+1)%ring.length];
    const dx=b[0]-a[0], dy=b[1]-a[1], length=dx*dx+dy*dy;
    const t=length ? Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)) : 0;
    best=Math.min(best,(p[0]-a[0]-t*dx)**2+(p[1]-a[1]-t*dy)**2);
  }
  return Math.sqrt(best);
}

test.beforeEach(async ({ page }) => {
  // Deterministic imagery makes leaks and interior overpainting measurable.
  await page.route('https://service.pdok.nl/hwh/luchtfotorgb/wmts/**', route => route.fulfill({ contentType:'image/png', body:fixture }));
  await page.route('https://tiles.openfreemap.org/**', route => route.request().url().endsWith('/planet')
    ? route.fulfill({contentType:'application/json',body:'{}'})
    : route.fulfill({contentType:'application/x-protobuf',body:Buffer.alloc(0)}));
  await page.route('**/tiles/satellite/**', route => route.fulfill({ contentType:'image/png', body:fixture }));
  await page.route('**/tiles/vector/**', route => route.fulfill({ contentType:'application/x-protobuf', body:Buffer.alloc(0) }));
  await page.goto('/?mode=satellite&zoom=11&weather=off');
  await page.waitForFunction(() => window.map?.getLayer('coastal-ocean')?.implementation?.program);
  await page.addStyleTag({ content: '.city-shell, .weather-hud, .layer-control-wrapper {display:none!important}' });
});

for (const camera of [
  { zoom:8, center:[4.49,51.93] },
  { zoom:11, center:[4.49,51.93] },
  { zoom:12, center:[4.59,51.986] },
  { zoom:15, center:[4.594,51.991], bearing:37, pitch:65 },
  { zoom:20, center:[4.3793095,51.9634066] }
]) test(`ocean pixels and precise cutout at zoom ${camera.zoom}`, async ({page}) => {
  const errors=[];page.on('pageerror', e=>errors.push(e.message));
  await page.evaluate(camera => map.jumpTo(camera), camera);
  await page.waitForFunction(() => map.areTilesLoaded());
  await page.evaluate(() => new Promise(resolve => { map.once('render', resolve); map.triggerRepaint(); }));
  const locations = await page.evaluate(() => {
    const values=[];
    for(let y=80;y<850;y+=53)for(let x=60;x<1150;x+=59){
      const p=map.unproject([x+0.5,y+0.5]);
      const q=map.unproject([x+1.5,y+0.5]);
      values.push({x,y,lng:p.lng,lat:p.lat,pixelDegrees:Math.abs(p.lng-q.lng)});
    }
    return values;
  });
  const png=PNG.sync.read(await page.screenshot());
  let checked=0;
  for(const sample of locations){
    const d=distance(localPoint([sample.lng,sample.lat]));
    const inside=booleanPointInPolygon(point([sample.lng,sample.lat]),city);
    // Ignore edge coverage and the deliberate water-only interior transition.
    if(d < Math.max(inside ? 230 : 35,sample.pixelDegrees*70000*3))continue;
    const t=1-(1-Math.max(0,Math.min(1,(d-30)/3170)))**2;
    const expected=inside ? [210,70,180] : palette.coast.map((value,c)=>value+(palette.ocean[c]-value)*t);
    const index=(sample.y*png.width+sample.x)*4;
    for(let c=0;c<3;c++)expect(Math.abs(png.data[index+c]-expected[c]),`${JSON.stringify(sample)} channel ${c}`).toBeLessThan(4);
    checked++;
  }
  // At zoom 20, the view is all close shoreline: explicitly check both sides.
  if(camera.zoom===20){
    const colors=new Set();
    for(let i=0;i<png.data.length;i+=4)colors.add(`${png.data[i]},${png.data[i+1]},${png.data[i+2]}`);
    expect(colors.has('210,70,180')).toBeTruthy();
    expect(colors.has(palette.coast.join(','))).toBeTruthy();
  } else expect(checked).toBeGreaterThan(20);
  expect(errors).toEqual([]);
  expect(await page.evaluate(()=>map.painter.context.gl.getError())).toBe(0);
});

test('style switching, detail toggles and context restoration', async ({page}) => {
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  for(const mode of ['dark','satellite','clean','satellite']){
    await page.evaluate(async mode=>{const {switchStyle}=await import('/src/lib/map.js');switchStyle(map,mode,{labels:false,buildings3d:true});},mode);
    await page.waitForFunction(mode=>mode==='satellite'
      ? !!map.getLayer('coastal-ocean') && !!map.getLayer('coastal-river-blend')
      : !map.getLayer('coastal-ocean') && !map.getLayer('coastal-river-blend'),mode);
  }
  expect(await page.evaluate(()=>map.getStyle().layers.filter(l=>l.type==='symbol').every(l=>l.layout.visibility==='none'))).toBeTruthy();
  expect(await page.evaluate(()=>!!map.getLayer('3d-buildings-extrusion'))).toBeTruthy();
  await page.evaluate(()=>new Promise(resolve=>{
    map.once('webglcontextrestored',()=>{map.once('idle',resolve);});
    const extension=map.painter.context.gl.getExtension('WEBGL_lose_context');
    extension.loseContext();setTimeout(()=>extension.restoreContext(),100);
  }));
  expect(await page.evaluate(()=>map.painter.context.gl.isProgram(map.getLayer('coastal-ocean').implementation.program))).toBeTruthy();
  expect(await page.evaluate(()=>map.painter.context.gl.getError())).toBe(0);
  expect(errors).toEqual([]);
});

test('fixed-year PDOK imagery uses its finest tiles and keeps credits in Map settings', async ({page}) => {
  const tileRequests = [];
  page.on('request', request => {
    if (request.url().includes('/luchtfotorgb/')) tileRequests.push(request.url());
  });
  await page.evaluate(() => new Promise(resolve => {
    map.once('idle', resolve);
    map.jumpTo({ center: [4.4851, 51.9186], zoom: 20 });
  }));
  expect(tileRequests.length).toBeGreaterThan(0);
  expect(tileRequests.every(url => url.includes('/2026_orthoHR/'))).toBeTruthy();
  expect(tileRequests.some(url => url.includes('GoogleMapsCompatible/21/'))).toBeTruthy();
  expect(await page.evaluate(() => map.getStyle().sources.satellite.attribution)).toContain('Samenwerkingsverband Beeldmateriaal');
  await expect(page.locator('.maplibregl-ctrl-attrib')).toHaveCount(0);
  await page.addStyleTag({ content: '.city-shell {display:block!important}' });
  await page.getByRole('button', { name: 'Map', exact: true }).click();
  const credits = page.getByRole('region', { name: 'Map credits' });
  await credits.scrollIntoViewIfNeeded();
  await expect(credits).toContainText('Samenwerkingsverband Beeldmateriaal');
  await expect(credits.getByRole('link', { name: 'OpenStreetMap contributors', exact: true })).toHaveAttribute('href', 'https://www.openstreetmap.org/copyright');
  await expect(credits.getByRole('link', { name: 'CC BY 4.0', exact: true })).toHaveAttribute('href', 'https://creativecommons.org/licenses/by/4.0/');
  await page.getByRole('button', { name: 'Night', exact: true }).click();
  await expect.poll(() => page.evaluate(() => !!map.getStyle().sources.satellite)).toBe(false);
  await expect(page.locator('.maplibregl-ctrl-attrib')).toHaveCount(0);
});
