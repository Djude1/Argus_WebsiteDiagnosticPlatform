# 修正依賴時序的報告指紋測試（CI 紅燈）

**日期**：2026-09-05
**操作者**：Claude

## 變更內容

`tests_report_verification.ReportCacheTests.test_rebuild_keeps_the_previous_hash_verifiable`
改用哨兵指紋（`"d" * 64`）取代「比對重產後指紋有沒有變」。

## 原因

該測試在本機每次通過、在 CI 失敗：

```
AssertionError: 'e0f6b696…' == 'e0f6b696…'
```

斷言「重產一定產生不同指紋」的前提本身是錯的。兩次產生若落在同一秒，報告內的
產生時間字串相同，`.docx` 位元組完全一致，指紋當然不變。本機產生報告較慢、跨秒
所以看不出來，CI runner 快就會紅。

原本試圖用 `report_output_path(...).write_bytes(b"tampered")` 製造差異，但重產會
整個覆寫檔案，篡改的內容對新指紋毫無影響——註解裡甚至已經寫出這個風險，做法卻
達不到目的。

這個測試要驗的是「舊指紋有沒有被完整搬進 `previous_sha256`」，與位元組變不變無關。

## 影響範圍

- 僅測試檔案，產品程式碼未動。
- CI 失敗期間 image 仍被 build 且 bot 已回寫 `sha-98c7bee` 到 `kustomization.yaml`。

  **更正（2026-09-05 稍晚）**：先前這裡寫「Quality Gate 失敗不會擋住部署」是
  錯的推論，沒有去看 build 的 log 就下結論。`build-backend.yml` 本來就有
  「推送 image 前執行後端品質閘門」，跑的是同一套 ruff + check +
  makemigrations --check + 部署契約 + `test apps`；`98c7bee` 的 backend build
  log 顯示 `Ran 813 tests` 全數通過才繼續 build。`build-frontend.yml` 同理有
  `npm ci && npm run build`。

  真正發生的是：**同一個時序相依的測試在 Quality Gate 的 runner 上紅、在
  build runner 上綠**——這正好也是「flaky 測試比純粹的紅燈更難察覺」的實例。

  仍存在的真實落差是：build 的內建閘門是 Quality Gate 的**子集**，缺少
  `promote_kali_image.py --check`、k8s manifest 渲染斷言、repository-text
  檢查與 kali-runner 單元測試。也就是 k8s manifest 壞掉或 Kali digest 不一致
  時，image 仍然建得出來。

## 驗證方式

- 連跑 3 次 `ReportCacheTests` 皆 OK（原本受時序影響）
- 移除 `reports.py` 的 `previous_sha256` 保留邏輯後該測試**確實失敗**，
  確認仍抓得到迴歸
- 回頭檢查本次新增的其餘 7 個測試，斷言都建立在明確設定的哨兵值或 mock 呼叫
  次數上，無同類時序相依
- `ruff check backend` 通過
- `manage.py test apps` -> 813 tests OK (skipped=1)
