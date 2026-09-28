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
