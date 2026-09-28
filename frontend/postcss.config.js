import autoprefixer from "autoprefixer";
import tailwindcss from "tailwindcss";

import memberLegacyScope from "./postcss-member-legacy.js";

export default {
  plugins: [
    // tailwindcss 讀專案根的 tailwind.config.js；src/styles/legacy-member/ 以 @config 指定另一份
    tailwindcss,
    autoprefixer,
    // 必須排在 tailwind 之後：連同 tailwind 為 legacy-member 產生的 base／utilities 一起限縮範圍
    memberLegacyScope,
  ],
};
