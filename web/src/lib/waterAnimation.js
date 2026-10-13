/**
 * AnimatedOceanWater
 * Combines real North Sea satellite photography with a live 60 FPS wave displacement engine.
 * Animates primary ocean swells, secondary cross-currents, and solar caustic glints.
 */
export class AnimatedOceanWater {
  constructor(map) {
    this.map = map;
    this.canvas = document.createElement('canvas');
    this.canvas.width = 256;
    this.canvas.height = 256;
    this.ctx = this.canvas.getContext('2d');
    this.img = new Image();
    this.img.src = '/ocean_satellite.png';
    this.isRunning = false;
    this.animId = null;
    this.startTime = performance.now();
    this.isLoaded = false;

    this.img.onload = () => {
      this.isLoaded = true;
      this.init();
    };
  }

  init() {
    if (!this.map) return;
    this.drawFrame(0);
    if (!this.map.hasImage('animated-ocean-pattern')) {
      try {
        this.map.addImage('animated-ocean-pattern', this.canvas);
      } catch (e) {}
    }
  }

  start() {
    if (this.isRunning) return;
    this.isRunning = true;
    const loop = (now) => {
      if (!this.isRunning) return;
      const t = (now - this.startTime) * 0.001;
      this.drawFrame(t);

      if (this.map) {
        if (!this.map.hasImage('animated-ocean-pattern')) {
          try {
            this.map.addImage('animated-ocean-pattern', this.canvas);
          } catch (e) {}
        } else {
          try {
            this.map.updateImage('animated-ocean-pattern', this.canvas);
            this.map.triggerRepaint();
          } catch (e) {}
        }
      }

      this.animId = requestAnimationFrame(loop);
    };
    this.animId = requestAnimationFrame(loop);
  }

  stop() {
    this.isRunning = false;
    if (this.animId) {
      cancelAnimationFrame(this.animId);
      this.animId = null;
    }
  }

  drawFrame(t) {
    if (!this.isLoaded) return;
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    ctx.clearRect(0, 0, w, h);

    // Wave Layer 1: Primary deep ocean swell drifting steadily
    const dx1 = Math.sin(t * 0.35) * 14;
    const dy1 = Math.cos(t * 0.28) * 10;
    ctx.drawImage(this.img, -16 + dx1, -16 + dy1, w + 32, h + 32);

    // Wave Layer 2: Cross-current wave perturbation
    ctx.globalAlpha = 0.45;
    const dx2 = Math.cos(t * 0.55 + 1.3) * 12;
    const dy2 = Math.sin(t * 0.45 + 0.9) * 12;
    ctx.drawImage(this.img, -16 + dx2, -16 + dy2, w + 32, h + 32);

    // Wave Layer 3: Dynamic solar glint & caustic shimmer on wave crests
    ctx.globalAlpha = 0.2 + 0.08 * Math.sin(t * 1.4);
    ctx.drawImage(this.img, -16 - dx1 * 0.6, -16 - dy2 * 0.6, w + 32, h + 32);

    ctx.globalAlpha = 1.0;
  }
}
