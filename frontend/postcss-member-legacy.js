// PostCSS 外掛：把 src/styles/legacy-member/ 的舊版（462848b）樣式限縮在 .member-legacy 範圍內。
//
// 會員區 Dashboard／掃描／網域驗證／歷史／購點恢復為改版前的 JSX，但全站其他地方（導覽列、設定、
// 後台、公開頁）仍使用 Night Watch 改版後的樣式，兩套規則大量共用 class 名稱。做法：
//   1. 每條舊規則都加上 SCOPE 前綴；SCOPE 用 :is(.member-legacy, #<不存在的 id>) 把特異度墊到 ID 等級，
//      確保範圍內一律由舊規則勝出。
//   2. 範圍內元素先 all: revert（同樣是 ID 等級），擋掉新版規則對同名 class 的殘留影響；
//      svg、帶 width/height 屬性的元素與 ReactFlow 不重置，避免吃掉屬性提供的尺寸與繪圖樣式。
//   3. 只作用在外層框架的規則（:root／html／body／.argus-app／.argus-main）改掛到 SCOPE 或
//      「含有 SCOPE 的外層元素」上，其餘外層樣式維持新版。
//   4. 舊 keyframes 一律加 ml- 前綴，避免與新版同名動畫互相覆蓋。
//   5. 深色主題：舊版只有淺色。每條含顏色的規則自動產生一條 :root[data-theme="dark"] 版本，
//      依明度對映（淺底→深藍底、深字→淺字、淺框→暗框），色相保留，所以狀態色仍可辨識；
//      對映不理想的地方在 legacy-member/91-dark.css 手動覆寫。
import selectorParser from "postcss-selector-parser";

const SCOPE = ":is(.member-legacy, #argus-member-legacy-scope)";
const FRAME_CLASSES = new Set(["argus-app", "argus-main", "with-nav"]);
const ROOT_TAGS = new Set(["html", "body"]);

function isFrameCompound(nodes) {
  return nodes.length > 0 && nodes.every((n) =>
    (n.type === "tag" && ROOT_TAGS.has(n.value)) ||
    (n.type === "pseudo" && n.value === ":root") ||
    n.type === "attribute" ||
    (n.type === "class" && FRAME_CLASSES.has(n.value)));
}

function isDocumentRoot(nodes) {
  return nodes.some((n) => (n.type === "tag" && ROOT_TAGS.has(n.value)) || (n.type === "pseudo" && n.value === ":root"));
}

function scopeSelector(selector) {
  const results = [];
  selectorParser().astSync(selector).each((complex) => {
    const compounds = [[]];
    for (const node of complex.nodes) {
      if (node.type === "combinator") compounds.push([]);
      else compounds[compounds.length - 1].push(node);
    }
    const texts = compounds.map((c) => c.map(String).join("").trim());
    let frameCount = 0;
    while (frameCount < compounds.length && isFrameCompound(compounds[frameCount])) frameCount++;

    let result;
    if (frameCount < compounds.length) {
      // 一般規則：外層框架前綴保留，其後接 SCOPE，再接原本的頁面選擇器（組合子一律視為後代）
      const rest = complex.nodes.slice(complex.nodes.indexOf(compounds[frameCount][0]));
      result = [...texts.slice(0, frameCount), SCOPE, rest.map(String).join("").trim()].join(" ");
    } else {
      const last = compounds[compounds.length - 1];
      const before = texts.slice(0, -1);
      if (isDocumentRoot(last)) {
        // :root / html / body 的 token 與字型：改掛在 SCOPE 上，讓範圍內元素繼承
        const conditions = last.filter((n) => n.type === "attribute").map(String).join("");
        result = [...before, conditions ? `:root${conditions}` : "", SCOPE].filter(Boolean).join(" ");
      } else {
        // .argus-app／.argus-main 本身：只在它包含 SCOPE 時套用
        result = [...before, `${texts[texts.length - 1]}:has(${SCOPE})`].join(" ");
      }
    }
    results.push(result);
  });
  return results.join(", ");
}

// ── 深色主題對映 ───────────────────────────────────────────────
const BG_PROPS = /^(background|background-color|background-image|--tw-gradient-(from|via|to|stops))$/;
const TEXT_PROPS = /^(color|fill|stroke|caret-color|text-decoration-color|-webkit-text-fill-color|accent-color)$/;
const BORDER_PROPS = /^(border(-(top|right|bottom|left))?(-color)?|outline(-color)?|--tw-ring-color|--tw-divide-color|column-rule-color)$/;
const COLOR_RE = /#([0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3,4})\b|rgba?\(\s*([\d.]+%?)\s*[,\s]\s*([\d.]+%?)\s*[,\s]\s*([\d.]+%?)\s*(?:[,/]\s*(var\([^()]*\)|[\d.]+%?)\s*)?\)|\bwhite\b/gi;

function parseChannel(v) {
  return v.endsWith("%") ? (parseFloat(v) * 255) / 100 : parseFloat(v);
}

function toHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h;
  if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return [h * 60, s, l];
}

function mapLightness(kind, h, s, l) {
  const neutral = s < 0.2;
  if (kind === "bg") {
    if (l < 0.8) return null;
    // 淺中性底 → 深藍面：越淺（白）對映越亮，保留「卡片比頁面亮」的層次
    if (neutral) return [222, 0.5, Math.max(0.05, 0.12 - (1 - l) * 0.55)];
    return [h, Math.min(s, 0.75) * 0.55, 0.13 + (1 - l) * 0.35];
  }
  if (kind === "text") {
    if (l > 0.62) return null;
    return [h, neutral ? Math.min(s, 0.2) : s, 0.97 - l * 0.62];
  }
  if (l < 0.8) return null; // border
  if (neutral) return [215, 0.35, 0.16 + (1 - l) * 0.7];
  return [h, Math.min(s, 0.75) * 0.6, 0.2 + (1 - l) * 0.6];
}

function mapColor(kind, match, hex, r, g, b, alpha) {
  let rgb;
  let a = alpha;
  if (hex) {
    const full = hex.length <= 4 ? hex.split("").map((c) => c + c).join("") : hex;
    rgb = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16));
    if (full.length === 8) a = (parseInt(full.slice(6, 8), 16) / 255).toFixed(3);
  } else if (r !== undefined) {
    rgb = [parseChannel(r), parseChannel(g), parseChannel(b)];
  } else {
    rgb = [255, 255, 255];
  }
  const [h, s, l] = toHsl(...rgb);
  const mapped = mapLightness(kind, h, s, l);
  if (!mapped) return match;
  const [nh, ns, nl] = mapped;
  const hsl = `${nh.toFixed(1)} ${(ns * 100).toFixed(1)}% ${(Math.min(Math.max(nl, 0), 1) * 100).toFixed(1)}%`;
  return a !== undefined ? `hsl(${hsl} / ${a})` : `hsl(${hsl})`;
}

function darkValue(prop, value) {
  const kind = BG_PROPS.test(prop) ? "bg" : TEXT_PROPS.test(prop) ? "text" : BORDER_PROPS.test(prop) ? "border" : null;
  if (!kind) return null;
  const next = value.replace(COLOR_RE, (...m) => mapColor(kind, ...m.slice(0, 6)));
  return next === value ? null : next;
}

function darkSelector(selector) {
  if (/data-theme/.test(selector)) return null;
  return selector
    .split(/,(?![^(]*\))/)
    .map((s) => s.trim())
    .map((s) => (/^(:root|html)\b/.test(s) ? s.replace(/^(:root|html)/, "$1[data-theme=\"dark\"]") : `:root[data-theme="dark"] ${s}`))
    .join(", ");
}

function addDarkClones(root) {
  const rules = [];
  root.walkRules((r) => {
    if (r.parent?.type === "atrule" && /keyframes$/.test(r.parent.name)) return;
    rules.push(r);
  });
  for (const r of rules) {
    const selector = darkSelector(r.selector);
    if (!selector) continue;
    const decls = [];
    r.each((node) => {
      if (node.type !== "decl") return;
      const value = darkValue(node.prop, node.value);
      if (value) decls.push(node.clone({ value }));
    });
    if (decls.length) r.cloneAfter({ selector, nodes: decls });
  }
}

export default function memberLegacyScope() {
  return {
    postcssPlugin: "argus-member-legacy-scope",
    OnceExit(root, { rule, decl }) {
      const file = (root.source?.input?.file || "").replaceAll("\\", "/");
      if (!file.includes("/styles/legacy-member/")) return;

      const names = new Set();
      root.walkAtRules(/keyframes$/, (at) => {
        names.add(at.params);
        at.params = `ml-${at.params}`;
      });
      if (names.size) {
        const pattern = new RegExp(`(^|[\\s,])(${[...names].map((n) => n.replace(/[-]/g, "\\-")).join("|")})(?=$|[\\s,])`, "g");
        root.walkDecls(/^(-webkit-)?animation(-name)?$/, (d) => {
          d.value = d.value.replace(pattern, "$1ml-$2");
        });
      }

      addDarkClones(root);

      root.walkRules((r) => {
        if (r.parent?.type === "atrule" && /keyframes$/.test(r.parent.name)) return;
        r.selectors = r.selectors.map(scopeSelector);
      });

      const keep = ":not(svg, svg *, [width], [height], .react-flow, .react-flow *)";
      root.prepend(
        rule({ selector: SCOPE }).append(decl({ prop: "display", value: "contents" })),
        rule({ selector: `${SCOPE} :where(${keep}), ${SCOPE} :where(${keep})::before, ${SCOPE} :where(${keep})::after` })
          .append(decl({ prop: "all", value: "revert" })),
      );
    },
  };
}
memberLegacyScope.postcss = true;
