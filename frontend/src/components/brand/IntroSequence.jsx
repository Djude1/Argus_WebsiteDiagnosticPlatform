import { useEffect, useRef, useState } from "react";

// 首次進站的品牌開場：字元粒子風暴 → 聚合成 Argus 標誌（杏眼＋12 顆虹膜小眼＋琥珀反光）
// 與 ARGUS 字標 → 放射穿越後淡出。
//
// 聚合目標直接用向量幾何畫在離屏 canvas 上取樣（與 ArgusMark.tsx 同一組路徑），
// 不再載入 164 KB 的點陣 logo：任何解析度都清晰，也少一次網路請求。
// 顏色取品牌原色（虹膜青為主、守望琥珀只在反光點與少量粒子）。
// 開場固定是深色畫面，不隨日／夜主題切換。

const INTRO_PHASE = { storm: 2000, assemble: 2400, display: 400, warp: 2200 };
const INTRO_TOTAL =
  INTRO_PHASE.storm + INTRO_PHASE.assemble + INTRO_PHASE.display + INTRO_PHASE.warp;
const INTRO_STORM_CHARS = "01ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$&*+={}/<>";
const INTRO_ARGUS_CHARS = "ARGUS";
// 品牌原色（對應 03-tokens.css 的 --ag-iris-* / --ag-signal-*）
const BRAND = {
  iris200: "#b4f3fa",
  iris300: "#7fe9f5",
  iris400: "#3fdcee",
  iris600: "#0a9db8",
  signal400: "#ffc04d",
  text: "#e8eef8",
};
// 風暴粒子：8 色輪替，其中 1 色是守望琥珀——點綴，不搶主色
const INTRO_STORM_COLORS = [
  "rgba(63, 220, 238, 0.6)", "rgba(127, 233, 245, 0.7)", "rgba(20, 195, 221, 0.62)",
  "rgba(180, 243, 250, 0.55)", "rgba(63, 220, 238, 0.75)", "rgba(255, 192, 77, 0.55)",
  "rgba(10, 157, 184, 0.7)", "rgba(127, 233, 245, 0.62)",
];
// 放射穿越光束色盤：虹膜青階＋白（琥珀只留在標誌反光點與少量風暴粒子）
const INTRO_WARP_COLORS = [
  [63, 220, 238],
  [127, 233, 245],
  [180, 243, 250],
  [20, 195, 221],
  [10, 157, 184],
  [232, 238, 248],
  [255, 255, 255],
];
// ArgusMark 的幾何（viewBox 0 0 48 48），與 components/brand/ArgusMark.tsx 相同
const MARK_LID_PATH = "M3.5 24C9.2 14.6 16.2 10 24 10s14.8 4.6 20.5 14C38.8 33.4 31.8 38 24 38S9.2 33.4 3.5 24Z";
const MARK_IRIS_DOTS = Array.from({ length: 12 }, (_, i) => {
  const angle = (i / 12) * Math.PI * 2 - Math.PI / 2;
  return { x: 24 + Math.cos(angle) * 8.6, y: 24 + Math.sin(angle) * 8.6 };
});

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
    let logoCanvas = null;
    let textTop = Infinity;
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

    // 把標誌與字標畫到離屏 canvas，再以固定間距取樣成粒子的聚合目標
    function buildTargets() {
      const cx = W / 2, cy = H / 2;
      const markSize = Math.min(W * 0.46, H * 0.42, 380);
      const k = markSize / 48;
      const markTop = cy - markSize * 0.62;
      const markLeft = cx - markSize / 2;
      const off = document.createElement("canvas");
      off.width = W; off.height = H;
      const octx = off.getContext("2d");

      octx.save();
      octx.translate(markLeft, markTop);
      octx.scale(k, k);
      const grad = octx.createLinearGradient(6, 10, 42, 38);
      grad.addColorStop(0, BRAND.iris300);
      grad.addColorStop(1, BRAND.iris600);
      octx.strokeStyle = grad;
      octx.lineWidth = 2.6;
      octx.lineJoin = "round";
      octx.stroke(new Path2D(MARK_LID_PATH));
      octx.fillStyle = BRAND.iris400;
      for (const dot of MARK_IRIS_DOTS) {
        octx.beginPath(); octx.arc(dot.x, dot.y, 1.55, 0, Math.PI * 2); octx.fill();
      }
      octx.fillStyle = BRAND.text;
      octx.beginPath(); octx.arc(24, 24, 4.6, 0, Math.PI * 2); octx.fill();
      octx.fillStyle = BRAND.signal400;
      octx.beginPath(); octx.arc(26.3, 21.7, 1.35, 0, Math.PI * 2); octx.fill();
      octx.restore();

      // 字標：Sora 寬字距（字型未載入時退回系統無襯線，不影響取樣）
      const fontSize = Math.max(28, markSize * 0.26);
      octx.font = `700 ${fontSize}px Sora, "Noto Sans TC", system-ui, sans-serif`;
      octx.textBaseline = "middle";
      octx.fillStyle = BRAND.iris200;
      const tracking = fontSize * 0.34;
      const letters = INTRO_ARGUS_CHARS.split("");
      const widths = letters.map((ch) => octx.measureText(ch).width);
      const total = widths.reduce((sum, w) => sum + w, 0) + tracking * (letters.length - 1);
      let x = cx - total / 2;
      const textY = markTop + markSize * 0.92 + fontSize * 0.5;
      textTop = textY - fontSize * 0.6;
      letters.forEach((ch, i) => { octx.fillText(ch, x, textY); x += widths[i] + tracking; });
      logoCanvas = off;

      const data = octx.getImageData(0, 0, W, H).data;
      const pts = [];
      const step = W < 600 ? 4 : 5;
      for (let y = 0; y < H; y += step) {
        for (let x2 = 0; x2 < W; x2 += step) {
          const idx = (y * W + x2) * 4;
          if (data[idx + 3] > 80) pts.push({ x: x2, y, r: data[idx], g: data[idx + 1], b: data[idx + 2] });
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
            const inText = p.ty > textTop;
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
        if (p.size !== lastSize) { ctx.font = `700 ${p.size}px "JetBrains Mono", Consolas, monospace`; lastSize = p.size; }
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
        ctx.fillStyle = `rgba(6, 10, 20, ${trailFade})`;
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
        if (logoCanvas) ctx.drawImage(logoCanvas, 0, 0);
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

    const onResize = () => { resize(); };
    window.addEventListener("resize", onResize);
    // 點畫面任一處 / Esc / Enter / 空白鍵 皆可跳過動畫
    const onKey = (e) => {
      if (e.key === "Escape" || e.key === "Enter" || e.key === " ") { e.preventDefault(); finish(); }
    };
    window.addEventListener("keydown", onKey);

    buildTargets();
    startTime = performance.now();
    fpsTimer = startTime;
    mainRAF = requestAnimationFrame(mainLoop);

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
      <div className="argus-intro-hint">點擊任意處或按 Esc 跳過</div>
    </div>
  );
}

export default IntroSequence;
