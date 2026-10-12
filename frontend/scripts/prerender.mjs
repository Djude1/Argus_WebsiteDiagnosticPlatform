// 建置後預先渲染公開頁（2026-10-12，Argus 自掃「核心內容高度依賴 JavaScript 渲染」）：
// SPA 的 index.html 只有空的 <div id="root">，不執行 JavaScript 的爬蟲與 AI 讀不到內容。
// 這裡用 SSR bundle（dist-ssr/）把每個公開頁渲染成 dist/<路徑>.html（/ 是 dist/root.html），
// nginx 以 try_files $uri.html 提供，瀏覽器端由 main.jsx hydrate 接手。
// 頁面清單是 App.jsx 的 PRERENDERED_ROUTES；會員區、後台不預先渲染（需要登入、內容因人而異）。
import { readFile, rm, writeFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const dist = `${root}dist`;
const ssrDir = `${root}dist-ssr`;

function escapeHtml(text) {
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

function setMeta(html, attr, key, value) {
  const pattern = new RegExp(`(<meta ${attr}="${key}" content=")[^"]*(")`);
  if (!pattern.test(html)) throw new Error(`index.html 缺少 <meta ${attr}="${key}">`);
  return html.replace(pattern, `$1${escapeHtml(value)}$2`);
}

const template = await readFile(`${dist}/index.html`, "utf8");
if (!template.includes('<div id="root"></div>')) throw new Error('index.html 缺少 <div id="root"></div>');
const { render, titleForPath, descriptionForPath, PRERENDERED_ROUTES } = await import(pathToFileURL(`${ssrDir}/entry-server.js`).href);

for (const route of Object.keys(PRERENDERED_ROUTES)) {
  const body = await render(route);
  if (!body.includes("<main") || body.includes("正在載入頁面")) throw new Error(`${route} 沒有渲染出完整內容`);
  const title = titleForPath(route);
  const description = descriptionForPath(route);
  let html = template
    .replace(/<title>[^<]*<\/title>/, `<title>${escapeHtml(title)}</title>`)
    .replace('<div id="root"></div>', `<div id="root">${body}</div>`);
  html = setMeta(html, "name", "description", description);
  html = setMeta(html, "property", "og:title", title);
  html = setMeta(html, "property", "og:description", description);
  html = setMeta(html, "name", "twitter:title", title);
  html = setMeta(html, "name", "twitter:description", description);
  const file = route === "/" ? "root" : route.slice(1);
  await writeFile(`${dist}/${file}.html`, html);
  console.log(`prerendered ${route} → ${file}.html`);
}

await rm(ssrDir, { recursive: true, force: true });
