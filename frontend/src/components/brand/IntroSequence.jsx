import { useEffect, useMemo, useRef, useState } from "react";

import brandLogo from "../../assets/brand-logo.webp";

const INTRO_PHASE = { storm: 2000, assemble: 2400, display: 400, warp: 2200 };
const INTRO_TOTAL =
  INTRO_PHASE.storm + INTRO_PHASE.assemble + INTRO_PHASE.display + INTRO_PHASE.warp;
const INTRO_STORM_CHARS = "01ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$&*+={}/<>";
const INTRO_ARGUS_CHARS = "ARGUS";
const INTRO_STORM_COLORS = [
  "rgba(80, 220, 255, 0.55)", "rgba(100, 235, 255, 0.7)", "rgba(60, 200, 240, 0.65)",
  "rgba(140, 240, 255, 0.6)", "rgba(70, 210, 250, 0.75)", "rgba(170, 245, 255, 0.55)",
  "rgba(40, 180, 220, 0.65)", "rgba(110, 230, 255, 0.7)",
];
// 時空穿越光束色盤（沿用開頭動畫的青藍系，不另加雜色）
const INTRO_WARP_COLORS = [
  [56, 189, 248],   // argus-cyan
  [103, 232, 249],  // cyan-glow
  [125, 211, 252],  // sky
  [14, 165, 233],   // cyan-dot
  [150, 220, 255],  // 淺藍
  [224, 242, 254],  // 近白 cyan tint
  [255, 255, 255],  // 白
];

function IntroSequence({ onComplete }) {
  const canvasRef = useRef(null);
  const statusRef = useRef(null);
  const phaseRef = useRef(null);
  const timeRef = useRef(null);
  const fpsRef = useRef(null);
  const countRef = useRef(null);
  const finishRef = useRef(null);
  const completeRef = useRef(onComplete);
  completeRef.current = onComplete;
  const [fading, setFading] = useState(false);

  useEffect(() => {
    const prefersReduced =
      window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) {
      if (completeRef.current) completeRef.current();
      return undefined;
    }
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d", { alpha: true });
    let W = 0, H = 0;
    let particles = [];
    let imgRef = null;
    let logoBox = null;
    let fallbackCanvas = null;
    let warpInited = false;
    let startTime = 0, fpsCount = 0, fpsTimer = 0;
    let mainRAF = null;
    let finished = false;
    let finishTimer = null;

    function resize() {
      W = window.innerWidth; H = window.innerHeight;
      canvas.width = W; canvas.height = H;
    }
    resize();

    function buildLogoBox() {
      if (!imgRef) return;
      const maxW = Math.min(W * 0.6, 720);
      const maxH = Math.min(H * 0.6, 540);
      const ratio = imgRef.width / imgRef.height;
      let tw, th;
      if (maxW / ratio < maxH) { tw = maxW; th = maxW / ratio; }
      else { th = maxH; tw = maxH * ratio; }
      logoBox = { ox: (W - tw) / 2, oy: (H - th) / 2, tw, th };
    }

    function makeParticles(pts) {
      for (let i = pts.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [pts[i], pts[j]] = [pts[j], pts[i]];
      }
      const N = Math.min(pts.length, 1000);
      const cx = W / 2, cy = H / 2;
      const arr = new Array(N);
      for (let i = 0; i < N; i++) {
        const t = pts[i];
        const ang = Math.random() * Math.PI * 2;
        const r0 = Math.max(W, H) * (0.7 + Math.random() * 0.5);
        const isArgus = Math.random() < 0.2;
        arr[i] = {
          tx: t.x, ty: t.y,
          x: cx + Math.cos(ang) * r0, y: cy + Math.sin(ang) * r0,
          r: t.r, g: t.g, b: t.b,
          displayColor: `rgba(${Math.min(255, t.r + 50)}, ${Math.min(255, t.g + 50)}, ${Math.min(255, t.b + 50)}, 0.95)`,
          char: isArgus
            ? INTRO_ARGUS_CHARS[(Math.random() * 5) | 0]
            : INTRO_STORM_CHARS[(Math.random() * INTRO_STORM_CHARS.length) | 0],
          size: [9, 11, 13][(Math.random() * 3) | 0],
          sAng: Math.atan2(t.y - cy, t.x - cx) + (Math.random() - 0.5) * Math.PI,
          sDist: 120 + Math.random() * Math.max(W, H) * 0.5,
          sSpd: 0.5 + Math.random() * 1.5,
          changeTimer: Math.random() * 25,
          eAng: Math.atan2(t.y - cy, t.x - cx) + (Math.random() - 0.5) * 0.4,
          eSpd: 800 + Math.random() * 1400,
          phase: Math.random() * Math.PI * 2,
          locked: false,
        };
      }
      arr.sort((a, b) => a.size - b.size);
      particles = arr;
      if (countRef.current) countRef.current.textContent = String(N);
    }

    function buildFallback() {
      const cx = W / 2, cy = H / 2;
      const s = Math.min(W, H) / 900;
      const off = document.createElement("canvas");
      off.width = W; off.height = H;
      const octx = off.getContext("2d");
      octx.strokeStyle = "#0096ff"; octx.lineWidth = 12 * s;
      octx.beginPath(); octx.ellipse(cx, cy - 30 * s, 260 * s, 110 * s, 0, 0, Math.PI * 2); octx.stroke();
      octx.fillStyle = "#0066cc"; octx.beginPath(); octx.arc(cx, cy - 30 * s, 90 * s, 0, Math.PI * 2); octx.fill();
      octx.fillStyle = "#001a33"; octx.beginPath(); octx.arc(cx, cy - 30 * s, 40 * s, 0, Math.PI * 2); octx.fill();
      octx.fillStyle = "#00aaff";
      octx.font = `bold ${150 * s}px 'Arial Black', 'Impact', sans-serif`;
      octx.textAlign = "center"; octx.textBaseline = "middle";
      octx.fillText("ARGUS", cx, cy + 180 * s);
      fallbackCanvas = off;
      const data = octx.getImageData(0, 0, W, H).data;
      const pts = [];
      for (let y = 0; y < H; y += 5) {
        for (let x = 0; x < W; x += 5) {
          const idx = (y * W + x) * 4;
          if (data[idx + 3] > 80) pts.push({ x, y, r: data[idx], g: data[idx + 1], b: data[idx + 2] });
        }
      }
      makeParticles(pts);
    }

    function buildTargets() {
      if (!imgRef || !logoBox) { buildFallback(); return; }
      const { ox, oy, tw, th } = logoBox;
      const off = document.createElement("canvas");
      off.width = Math.floor(tw); off.height = Math.floor(th);
      const octx = off.getContext("2d");
      octx.drawImage(imgRef, 0, 0, off.width, off.height);
      let data;
      try { data = octx.getImageData(0, 0, off.width, off.height).data; }
      catch (e) { buildFallback(); return; }
      const w = off.width, h = off.height;
      const cornerIdx = [0, (w - 1) * 4, (h - 1) * w * 4, ((h - 1) * w + w - 1) * 4];
      let tCount = 0;
      for (const idx of cornerIdx) if (data[idx + 3] < 30) tCount++;
      const isTransparentBg = tCount >= 3;
      const pts = [];
      const step = 5;
      for (let y = 0; y < h; y += step) {
        for (let x = 0; x < w; x += step) {
          const idx = (y * w + x) * 4;
          const r = data[idx], g = data[idx + 1], b = data[idx + 2], a = data[idx + 3];
          let keep;
          if (isTransparentBg) keep = a > 40;
          else {
            const lum = (r + g + b) / 3 / 255;
            const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
            const sat = mx === 0 ? 0 : (mx - mn) / mx;
            keep = a > 60 && !(lum > 0.93 && sat < 0.06);
          }
          if (keep) pts.push({ x: ox + x, y: oy + y, r, g, b });
        }
      }
      makeParticles(pts);
    }

    function randomizeWarp(p) {
      // 不規則：每粒子隨機顏色 / 寬度 / 拉長長度 / 速度
      p.warpColor = INTRO_WARP_COLORS[(Math.random() * INTRO_WARP_COLORS.length) | 0];
      p.warpWidth = 2 + Math.random() * 9;        // 粗細不一
      p.warpLenK = 0.7 + Math.random() * 2.8;     // 拉長長度不一
      p.warpSpeedK = 0.6 + Math.random() * 1.2;   // 速度不一
    }
    function initWarp() {
      // 從粒子「目前位置」(剛聚合成 logo 的位置) 直接往外發射 →
      // logo 散開無縫接上時空穿越，中間不經過白色閃光。
      const cx = W / 2, cy = H / 2;
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        const dx = p.x - cx, dy = p.y - cy;
        p.warpAng = Math.atan2(dy, dx);
        p.warpDist = Math.max(2, Math.hypot(dx, dy));
        randomizeWarp(p);
      }
    }

    function updateAndDraw(phase, pt, elapsed) {
      const cx = W / 2, cy = H / 2;
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      let lastSize = -1;
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        if (phase === "STORM") {
          const settle = pt * pt; const chaos = 1 - settle * 0.6;
          p.sAng += p.sSpd * 0.011 * chaos;
          p.sDist -= settle * 1.4;
          const maxR = Math.max(W, H) * (0.7 - settle * 0.35);
          if (p.sDist < 60) p.sDist = 60; if (p.sDist > maxR) p.sDist = maxR;
          const slow = elapsed * 0.001;
          const w1 = Math.sin(slow + p.phase) * 50 * chaos;
          const w2 = Math.cos(slow * 1.4 + p.phase * 2.3) * 35 * chaos;
          const driftX = Math.sin(slow * 0.6 + p.phase * 3.7) * 28 * chaos;
          const driftY = Math.cos(slow * 0.9 + p.phase * 1.7) * 32 * chaos;
          const r = p.sDist + w1 + w2;
          const sx = cx + Math.cos(p.sAng) * r * 1.3 + driftX;
          const sy = cy + Math.sin(p.sAng) * r * 0.8 + driftY;
          const lerpK = Math.max(0, settle - 0.15) * 0.11;
          p.x = sx + (p.tx - sx) * lerpK; p.y = sy + (p.ty - sy) * lerpK;
          p.changeTimer--;
          if (p.changeTimer < 0) {
            p.char = INTRO_STORM_CHARS[(Math.random() * INTRO_STORM_CHARS.length) | 0];
            p.changeTimer = 10 + Math.random() * 25;
          }
        } else if (phase === "ASSEMBLE") {
          const k = 0.08 + pt * 0.09;
          p.x += (p.tx - p.x) * k; p.y += (p.ty - p.y) * k;
          if (pt > 0.8) {
            const blend = (pt - 0.8) / 0.2;
            const breath = Math.sin(elapsed * 0.003 + p.phase) * 1;
            p.x = p.x * (1 - blend) + (p.tx + breath) * blend;
            p.y = p.y * (1 - blend) + (p.ty + breath * 0.5) * blend;
          }
          if (pt > 0.6 && !p.locked) {
            const inText = (p.ty - cy) > 60;
            if (inText && Math.random() < 0.55) p.char = INTRO_ARGUS_CHARS[(Math.random() * 5) | 0];
            p.locked = true;
          } else if (!p.locked) {
            p.changeTimer--;
            if (p.changeTimer < 0) {
              p.char = INTRO_STORM_CHARS[(Math.random() * INTRO_STORM_CHARS.length) | 0];
              p.changeTimer = 10 + Math.random() * 20;
            }
          }
        } else if (phase === "DISPLAY") {
          const breath = Math.sin(elapsed * 0.003 + p.phase) * 1;
          p.x = p.tx + breath; p.y = p.ty + breath * 0.5;
        }
        let fill;
        if (phase === "STORM") fill = INTRO_STORM_COLORS[i & 7];
        else if (phase === "ASSEMBLE") fill = pt > 0.5 ? p.displayColor : INTRO_STORM_COLORS[i & 7];
        else fill = p.displayColor;
        if (p.size !== lastSize) { ctx.font = `bold ${p.size}px 'Consolas', monospace`; lastSize = p.size; }
        ctx.fillStyle = fill;
        ctx.fillText(p.char, p.x, p.y);
      }
    }

    function mainLoop(now) {
      const elapsed = now - startTime;
      fpsCount++;
      if (now - fpsTimer > 500) {
        if (fpsRef.current) fpsRef.current.textContent = String(Math.round(fpsCount * 1000 / (now - fpsTimer)));
        fpsCount = 0; fpsTimer = now;
      }
      if (timeRef.current) timeRef.current.textContent = (elapsed / 1000).toFixed(1).padStart(4, "0");
      const P = INTRO_PHASE;
      let phaseName, pt;
      if (elapsed < P.storm) { phaseName = "STORM"; pt = elapsed / P.storm; }
      else if (elapsed < P.storm + P.assemble) { phaseName = "ASSEMBLE"; pt = (elapsed - P.storm) / P.assemble; }
      else if (elapsed < P.storm + P.assemble + P.display) { phaseName = "DISPLAY"; pt = (elapsed - P.storm - P.assemble) / P.display; }
      else if (elapsed < INTRO_TOTAL) { phaseName = "WARP"; pt = (elapsed - P.storm - P.assemble - P.display) / P.warp; }
      else { if (finishRef.current) finishRef.current(); return; }
      if (phaseRef.current) phaseRef.current.textContent = phaseName;
      const STATUS_MAP = { STORM: "ANALYZING", ASSEMBLE: "CONVERGING", DISPLAY: "LOCKED-ON", WARP: "HYPERSPACE" };
      if (statusRef.current) statusRef.current.textContent = STATUS_MAP[phaseName];

      if (phaseName === "WARP") {
        if (!warpInited) { initWarp(); warpInited = true; }
        const zoom = 1 + pt * pt * 0.65;
        canvas.style.transform = `scale(${zoom})`;
        // 觀測者越來越快 → 每幀清除越少、上一幀殘留越久 → 粒子拉出長殘影拖曳
        const trailFade = Math.max(0.05, 0.2 - pt * 0.15);
        ctx.fillStyle = `rgba(12, 16, 38, ${trailFade})`;
        ctx.fillRect(0, 0, W, H);
        const cxw = W / 2, cyw = H / 2;
        const baseSpeed = 5 + pt * pt * 80;
        const maxD = Math.max(W, H) * 1.35;
        for (let i = 0; i < particles.length; i++) {
          const p = particles[i];
          p.warpDist += baseSpeed * p.warpSpeedK;
          if (p.warpDist > maxD) {
            // 回收：隨機角度 + 重抽顏色/寬/長 → 持續不規則放射
            p.warpDist = Math.random() * 40;
            p.warpAng = Math.random() * Math.PI * 2;
            randomizeWarp(p);
          }
          const cosA = Math.cos(p.warpAng), sinA = Math.sin(p.warpAng);
          const x = cxw + cosA * p.warpDist, y = cyw + sinA * p.warpDist;
          // 拉長：長度隨距離增加且每粒子不一
          const tailLen = (baseSpeed * 1.5 + p.warpDist * 0.3) * p.warpLenK;
          const tx = cxw + cosA * (p.warpDist - tailLen), ty = cyw + sinA * (p.warpDist - tailLen);
          // 外端寬、內端收尖的錐形（垂直方向取半寬）
          const hw = p.warpWidth * Math.min(1, p.warpDist / 200);
          const px = -sinA, py = cosA;
          const a = Math.min(0.82, p.warpDist / 130);
          const c = p.warpColor;
          ctx.fillStyle = `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a})`;
          ctx.beginPath();
          ctx.moveTo(tx, ty);                   // 內端尖點
          ctx.lineTo(x + px * hw, y + py * hw); // 外端一側
          ctx.lineTo(x - px * hw, y - py * hw); // 外端另一側
          ctx.closePath();
          ctx.fill();
        }
        mainRAF = requestAnimationFrame(mainLoop);
        return;
      }

      ctx.clearRect(0, 0, W, H);
      let logoAlpha = 0;
      if (phaseName === "ASSEMBLE") logoAlpha = pt * 0.9;
      else if (phaseName === "DISPLAY") logoAlpha = 0.9 + Math.sin(elapsed * 0.003) * 0.08;
      if (logoAlpha > 0) {
        ctx.save(); ctx.globalAlpha = logoAlpha;
        if (imgRef && logoBox) ctx.drawImage(imgRef, logoBox.ox, logoBox.oy, logoBox.tw, logoBox.th);
        else if (fallbackCanvas) ctx.drawImage(fallbackCanvas, 0, 0);
        ctx.restore();
      }
      updateAndDraw(phaseName, pt, elapsed);
      mainRAF = requestAnimationFrame(mainLoop);
    }

    function finish() {
      if (finished) return;
      finished = true;
      if (mainRAF) cancelAnimationFrame(mainRAF);
      setFading(true);
      finishTimer = window.setTimeout(() => { if (completeRef.current) completeRef.current(); }, 650);
    }
    finishRef.current = finish;

    const onResize = () => { resize(); if (imgRef) buildLogoBox(); };
    window.addEventListener("resize", onResize);
    // 點畫面任一處 / Esc / Enter / 空白鍵 皆可跳過動畫
    const onKey = (e) => {
      if (e.key === "Escape" || e.key === "Enter" || e.key === " ") { e.preventDefault(); finish(); }
    };
    window.addEventListener("keydown", onKey);

    const img = new Image();
    img.onload = () => { imgRef = img; buildLogoBox(); buildTargets(); startTime = performance.now(); fpsTimer = startTime; mainRAF = requestAnimationFrame(mainLoop); };
    img.onerror = () => { buildFallback(); startTime = performance.now(); fpsTimer = startTime; mainRAF = requestAnimationFrame(mainLoop); };
    img.src = brandLogo;

    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("keydown", onKey);
      if (mainRAF) cancelAnimationFrame(mainRAF);
      if (finishTimer) clearTimeout(finishTimer);
    };
  }, []);

  return (
    <div
      className={`argus-intro ${fading ? "argus-intro--out" : ""}`}
      role="presentation"
      onClick={() => { if (finishRef.current) finishRef.current(); }}
    >
      <div className="argus-intro-grid" />
      <canvas ref={canvasRef} className="argus-intro-canvas" />
      <span className="argus-intro-corner tl" />
      <span className="argus-intro-corner tr" />
      <span className="argus-intro-corner bl" />
      <span className="argus-intro-corner br" />
      <div className="argus-intro-hud tl">
        <span className="dim">SYS://</span> <span className="v">ARGUS-CORE</span><br />
        <span className="dim">VER</span> <span className="v">v3.14.59</span><br />
        <span className="dim">NODE</span> <span className="v">ATHENS-07</span>
      </div>
      <div className="argus-intro-hud tr">
        <span className="dim">STATUS</span> <span className="v" ref={statusRef}>STAND-BY</span><br />
        <span className="dim">PHASE</span> <span className="v" ref={phaseRef}>--</span><br />
        <span className="dim">TIME</span> <span className="v" ref={timeRef}>00.0</span><span className="dim">s</span>
      </div>
      <div className="argus-intro-hud br">
        <span className="dim">PARTICLES</span> <span className="v" ref={countRef}>0</span><br />
        <span className="dim">FPS</span> <span className="v" ref={fpsRef}>--</span>
      </div>
      <div className="argus-intro-hint">點擊任意處跳過</div>
    </div>
  );
}

// ============================================================
// 根 App + Routes
// ============================================================

export default IntroSequence;
