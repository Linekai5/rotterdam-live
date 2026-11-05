<script>
  export let name = 'pin';
  export let size = 18;
  const paths = {
    spark: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z',
    district: 'M3 5 9 3l6 2 6-2v16l-6 2-6-2-6 2V5Zm6-2v16m6-14v16',
    shop: 'M4 10v10h16V10M3 10l2-6h14l2 6M3 10c1 2 3 2 4 0 1 2 3 2 5 0 2 2 4 2 5 0 1 2 3 2 4 0M9 20v-6h6v6',
    pin: 'M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0ZM9 10a3 3 0 1 0 6 0 3 3 0 0 0-6 0Z',
    route: 'M8 3 5 21m11-18 3 18M12 3v4m0 3v4m0 3v4',
    parking: 'M5 21V3h8a5 5 0 0 1 0 10H5m0 0v8',
    bridge: 'M3 16h18M6 5v14m12-14v14M6 7c4 7 8 7 12 0M3 12l3-5m12 0 3 5',
    works: 'M4 20h16M6 17l4-13h4l4 13M8 11h8M7 15h10',
    pulse: 'M2 12h5l3-8 4 16 3-8h5',
    report: 'M12 3 2 21h20L12 3Zm0 6v5m0 3v1',
    news: 'M5 4h16v15a2 2 0 0 1-2 2H5V4Zm0 4H2v11a2 2 0 0 0 3 2m4-13h8m-8 4h8m-8 4h4',
    leaf: 'M20 4C8 2 2 8 6 15c7 5 15-1 14-11ZM4 21 16 9',
    layers: 'm12 3 10 5-10 5L2 8l10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5',
    search: 'M16 16l5 5M4 10.5a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Z',
    arrow: 'M5 19 19 5M5 5h14v14',
    close: 'm6 6 12 12M6 18 18 6',
    reset: 'M4 10a8 8 0 1 1 2 8M4 4v6h6',
    compass: 'm16 8-3 5-5 3 3-5 5-3ZM3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0Z'
  };
</script>
<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d={paths[name] || paths.pin}/></svg>
