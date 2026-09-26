// ESLint 設定（flat config，ESLint 9）。
//
// 目的是抓「會在執行期出錯」的問題，不是統一風格：
//   · .jsx 不經過 TypeScript 檢查（checkJs: false），引用不存在的名稱時
//     build 照樣成功、要到瀏覽器才炸——no-undef 補的就是這個缺口
//   · hooks 規則：條件式呼叫 hook、useEffect 漏依賴
// 刻意不開：prop-types（改用 TypeScript）、排版類規則、react-hooks v7 新增的
// React Compiler 規則（對既有程式碼噪音過大，之後需要時再逐條評估）。
//
// ⚠ 固定 ESLint 9：eslint-plugin-react 7.37 的 peer 只到 ESLint 9.7。

import js from "@eslint/js";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["dist/**", "node_modules/**", "src/shared/apiTypes.ts", "public/**"],
  },
  {
    files: ["src/**/*.{js,jsx,ts,tsx}"],
    extends: [js.configs.recommended, react.configs.flat.recommended, react.configs.flat["jsx-runtime"]],
    plugins: { "react-hooks": reactHooks },
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...globals.browser },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    settings: { react: { version: "detect" } },
    rules: {
      "react/prop-types": "off",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // 以底線開頭的參數視為刻意不用（例如 (_, index) => ...）
      "no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      // 中文文案常刻意用全形空白（U+3000）排版，出現在字串與模板字串中是正常的
      "no-irregular-whitespace": ["error", { skipStrings: true, skipTemplates: true }],
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [tseslint.configs.recommended],
    rules: {
      // TS 自己會檢查未定義名稱，且比 no-undef 準（認得型別）
      "no-undef": "off",
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    },
  },
  {
    files: ["src/**/*.test.{ts,tsx,js,jsx}", "vitest.setup.ts"],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    files: ["*.config.js", "*.config.ts"],
    languageOptions: { globals: { ...globals.node } },
  },
);
