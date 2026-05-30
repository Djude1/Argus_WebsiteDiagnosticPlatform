# API Provider Workflow

## 目的

Argus Phase 2 需要 LLM Agent 與 tool calling。使用任何 API Key 前，必須先測試該 key 可用模型與能力，再選最符合專題需求的模型。

## 永遠禁止

- 不輸出 API Key、Token、密碼、私鑰、service account private key、完整憑證 JSON。
- 不把金鑰寫進程式碼、Markdown、log、git commit、final answer。
- 不輸出 provider 原始錯誤 body，因為其中可能含敏感資訊。

## 每次使用 API 前的安全流程

1. 從 `.env` 讀取變數名稱與是否有值，不輸出值。
2. 對 provider 呼叫官方模型列表或最小授權測試。
3. 記錄可公開摘要：provider、HTTP status、是否可列模型、模型 ID、是否支援文字生成、tool calling、context window 或其他公開能力。
4. 根據任務選模型：
   - Agent/tool calling：優先支援 tool calling 且已通過測試的模型。
   - GEO/AEO 文案與結構化分析：優先穩定、長上下文、成本可控的文字模型。
   - 若只需靜態掃描，不要呼叫 LLM。
5. 只在必要時做最小 chat/tool-call smoke test，prompt 不含任何秘密或使用者敏感資料。

## Provider fallback

- GLM 可用時可作為選項；若 GLM 回 429、授權失敗、配額不足、模型不可用或 tool calling 測試失敗，改用 Gemini 或 MiniMax。
- 專案中已放 MiniMax 設定；若 MiniMax models 與 tool-calling 測試通過，Phase 2 Agent 優先考慮 MiniMax。
- Gemini 可作為可用模型與文字分析 fallback；使用前仍需列舉可用模型與能力。

## 目前已知狀態

2026-05-20 的安全測試摘要：

- `MINIMAX_API_KEY`：存在；models 授權測試通過；tool-calling smoke test 通過。
- `GOOGLE_API_KEY`：存在；Gemini models 授權測試通過。
- `GLM_API_KEY`：存在；`glm-4.7-flash` 與 `glm-4.5-flash` chat/tool-calling smoke test 通過；`glm-5.1`、`glm-5-turbo`、`glm-5`、`glm-4.7`、`glm-4.6`、`glm-4.5-air`、`glm-4.5-airx` 當時回 HTTP 429；`glm-4-flash-250414`、`glm-4-flashx-250414` 當時回 HTTP 400。
- `GoogleCloud_ApiKey.json`：service account JSON 形狀正確，但不得輸出內容。

以上狀態只作歷史參考；每次實際使用前必須重新測試。

## 官方端點參考

- GLM chat/tool calling：`https://open.bigmodel.cn/api/paas/v4/chat/completions`
- MiniMax OpenAI-compatible models：`https://api.minimax.io/v1/models`
- MiniMax OpenAI-compatible chat：`https://api.minimax.io/v1/chat/completions`
- Gemini models list：`https://generativelanguage.googleapis.com/v1beta/models?key=<redacted>`

## 安全輸出格式

```text
PROVIDER_MODEL_LIST    pass    http=200    models=MiniMax-M2.7, MiniMax-M2.5
PROVIDER_TOOL_CALL     pass    http=200
```

不要輸出 headers、Authorization、request body 中的秘密、raw response。
