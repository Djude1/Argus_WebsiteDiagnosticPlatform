"""修正產出（Fix Output）產生引擎。

bounded 單次結構化產生：重用 Hermes 的 ProviderChain（MiniMax→GLM→Gemini）
做一次 JSON 輸出，再以事實政策三級驗證取代越界值，最終 artifacts 只含
爬取內容可支撐的值。非 agent 迴圈、不經 OpenCode、不經 Playwright。
"""
