# Domain Docs

工程類 skill 在探索本 repo 程式碼時，應如何消費領域文件。

## 探索前先讀

- 根目錄的 **`CONTEXT.md`**，或
- 根目錄的 **`CONTEXT-MAP.md`**（若存在）——它指向每個 context 一份 `CONTEXT.md`；讀與主題相關者。
- **`docs/adr/`**——讀與你即將動手區域相關的 ADR。多情境 repo 另查 `src/<context>/docs/adr/` 的 context 級決策。

若這些檔案不存在，**靜默繼續**。不要標記其缺失、不要預先建議建立。`/domain-modeling`（經 `/grill-with-docs`、`/improve-codebase-architecture` 抵達）會在詞彙或決策真正被釐清時惰性建立它們。

## 檔案結構

單一情境 repo（多數 repo）：

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

多情境 repo（根目錄存在 `CONTEXT-MAP.md` 時）：

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← 系統級決策
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← 該 context 專屬決策
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

> 本 repo 目前為**單一情境**（無 `CONTEXT-MAP.md`、無 monorepo 信號）。

## 使用詞彙表的用語

當你的輸出（issue 標題、重構提案、假說、測試名稱）提到某領域概念時，使用 `CONTEXT.md` 定義的術語，不要漂移到詞彙表刻意避開的同義詞。

若你需要的概念還不在詞彙表中，這是一個信號——不是你發明了專案不用的語言（重新考慮），就是真的有缺口（記下來給 `/domain-modeling`）。

## 標示與 ADR 衝突

若你的輸出與既有 ADR 衝突，明確點出，而非默默覆寫：

> _與 ADR-0007（event-sourced orders）衝突——但值得重議，因為…_
