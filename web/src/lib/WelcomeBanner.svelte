<script>
  import { onMount } from 'svelte';
  import artwork from '../../workercrew/RotterdamLiveUnderDevelopmentCrew.png';
  import { t } from './i18n.js';

  export let onDismiss = () => {};

  let dialog;

  onMount(() => dialog.showModal());
</script>

<dialog bind:this={dialog} aria-label={$t('Development notice')} aria-describedby="development-message" on:close={onDismiss} on:keydown|stopPropagation>
  <button type="button" on:click={() => dialog.close()} aria-label={$t('Dismiss development notice')}>
    <img
      id="development-message"
      src={artwork}
      alt={$t('Rotterdam Live is still in active development. Some things might not work yet.')}
      width="1679"
      height="937"
      draggable="false"
    />
    <span>{$t('Click anywhere to explore')}</span>
  </button>
</dialog>

<style>
  dialog {
    position: fixed;
    inset: 0;
    width: 100%;
    height: 100%;
    height: 100dvh;
    max-width: none;
    max-height: none;
    margin: 0;
    padding: 0;
    border: 0;
    background: transparent;
  }

  dialog::backdrop { background: #07131670; }

  button {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    width: 100%;
    height: 100%;
    padding: 24px 16px;
    border: 0;
    background: transparent;
    color: #f2f3ec;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }

  img {
    display: block;
    flex: 0 1 auto;
    width: auto;
    height: auto;
    min-height: 0;
    max-width: min(640px, 100%);
    max-height: calc(100dvh - 112px);
    object-fit: contain;
    filter: drop-shadow(0 14px 28px #0005);
    animation: welcome-in 280ms cubic-bezier(.2, .7, .3, 1) both;
  }

  span {
    font: 500 12px 'Instrument Sans', 'Helvetica Neue', Arial, sans-serif;
    letter-spacing: .025em;
    text-shadow: 0 1px 8px #000;
    animation: welcome-in 280ms ease-out both;
  }

  button:focus-visible { outline: none; }
  button:focus-visible span { text-decoration: underline; text-underline-offset: 4px; }

  @keyframes welcome-in {
    from { opacity: 0; transform: translateY(6px) scale(.98); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  @media (prefers-reduced-motion: reduce) {
    img, span { animation: none; }
  }
</style>
