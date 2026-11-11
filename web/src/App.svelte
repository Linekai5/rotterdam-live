<script>
  import MapComponent from './lib/MapComponent.svelte';
  import { language, setLanguage, t } from './lib/i18n.js';

  $: document.documentElement.lang = $language;
</script>

<svelte:head>
  <title>{$t('Rotterdam Live — Explore the city')}</title>
</svelte:head>

<main>
  <MapComponent />
  <div class="language-switch" role="group" aria-label={$t('Language')}>
    <button type="button" lang="nl" aria-label="Nederlands" aria-pressed={$language === 'nl'} on:click={() => setLanguage('nl')}>NL</button>
    <button type="button" lang="en" aria-label="English" aria-pressed={$language === 'en'} on:click={() => setLanguage('en')}>EN</button>
  </div>
</main>

<style>
  @font-face { font-family: 'Instrument Sans'; src: url('/fonts/InstrumentSans.ttf') format('truetype'); font-weight: 400 700; font-display: swap; }
  :global(html, body, #app) {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background-color: #082632;
    font-family: 'Instrument Sans', 'Helvetica Neue', Arial, sans-serif;
  }

  main {
    position: relative;
    width: 100%;
    height: 100%;
  }

  .language-switch {
    position: fixed;
    right: 24px;
    bottom: 24px;
    z-index: 15;
    display: flex;
    background: #171a19f5;
    border: 1px solid #ffffff29;
    border-radius: 3px;
  }
  .language-switch button {
    min-width: 38px;
    min-height: 36px;
    border: 0;
    background: transparent;
    color: #abb69f;
    font: 500 11px 'Instrument Sans', 'Helvetica Neue', Arial, sans-serif;
    letter-spacing: .07em;
    cursor: pointer;
  }
  .language-switch button + button { border-left: 1px solid #ffffff1c; }
  .language-switch button[aria-pressed='true'] { background: #bdc9b0; color: #242d20; }
  .language-switch button:focus-visible { outline: 2px solid #edf0e5; outline-offset: -3px; }
  @media (max-width: 700px) {
    .language-switch { right: 16px; bottom: 31px; }
    .language-switch button { min-width: 42px; min-height: 50px; }
  }
</style>
