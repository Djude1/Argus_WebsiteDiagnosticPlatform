// 會員區舊版樣式（src/styles/legacy-member/）專用的 Tailwind 設定：沿用 462848b 的設定（不含品牌字體），
// 讓範圍內的 preflight 與 utilities 與改版前一致。由 legacy-member/00-tailwind.css 的 @config 指定。
import baseConfig from "./tailwind.config.js";

/** @type {import('tailwindcss').Config} */
export default {
  content: baseConfig.content,
  theme: {
    extend: {},
  },
  plugins: [],
};
