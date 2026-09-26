/** @type {import('tailwindcss').Config} */
export default {
  // ts/tsx 也要掃，否則 .tsx 元件用到的 class 會被靜默 purge；
  // apiTypes.ts 是產生的型別檔、內容不受我們控制（上萬個字串），不讓它影響 CSS 輸出
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}", "!./src/shared/apiTypes.ts"],
  theme: {
    extend: {},
  },
  plugins: [],
};
