<script>
  import { onMount, onDestroy } from 'svelte';
  import { initMap } from './map.js';
  import LayerControl from './LayerControl.svelte';

  let mapElement;
  let map = null;

  onMount(async () => {
    try {
      console.log('MapComponent: calling initMap...');
      map = await initMap(mapElement, (loadedMap) => {
        console.log('MapComponent: onReady called!');
        map = loadedMap;
        if (typeof window !== 'undefined') window.map = loadedMap;
      });
      if (typeof window !== 'undefined') window.map = map;
      console.log('MapComponent: initMap returned!', !!map);
    } catch (err) {
      console.error('MapComponent: initMap error!', err);
    }
  });

  onDestroy(() => {
    if (map) {
      map.remove();
    }
  });

  const urlParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
  const initialMode = urlParams?.get('mode') || 'satellite';
  const defaultBg = initialMode === 'satellite' ? '#082632' : (initialMode === 'dark' ? '#0c0c0c' : '#c2c8ca');
</script>

<div class="map-wrapper">
  <div bind:this={mapElement} class="map-container" style="background-color: {defaultBg}"></div>
  <LayerControl {map} />
</div>

<style>
  .map-wrapper {
    position: fixed;
    inset: 0;
    width: 100vw;
    height: 100vh;
    overflow: hidden;
  }

  .map-container {
    width: 100%;
    height: 100%;
    position: absolute;
    inset: 0;
    background-color: #c2c8ca;
    transition: background-color 0.4s ease;
  }

  .map-container :global(:focus) {
    outline: none !important;
    box-shadow: none !important;
  }
</style>
