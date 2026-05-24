# 2026-05-20 避障 / ASR / TTS 三條鏈 Bug 完整交接

> 來源：2026-05-19 ~ 05-20 對話。為部署機測試 + 後續修復做交接。
> 撰寫 commit：本檔案本身

---

## 背景與環境狀態

### Commit 對應關係
| 角色 | Commit | 日期 | 備註 |
|------|--------|------|------|
| 部署機 server | `017c7f5` | 2026-05-11 | 9 天沒 git pull |
| `origin/main` | `0a51a93` | 2026-05-13 | server 含 15s timeout / 寬鬆 nav / WaveNet TTS |
| 本地 main | `ec3f2d0` | 2026-05-13 | APP 三 bug 修復（未 push、未實機驗證） |

### 部署機落後的內容（`017c7f5..origin/main`）
- `aa72c7b` 預錄缺失語音（4/21–5/11 log）
- `1c86d9e` viewer WS 公網斷線不重連修復
- `1f75b15` AR 測試介面 + .gitignore 補齊
- `1ff3ac6` 摔倒偵測全域化
- `3aa2647` docs(claude.md) 精簡
- `0a51a93` ASR/TTS/連線修復進度（**自承核心 bug 未解、WIP**）

### 觸發本次 review 的症狀
- APP 已 build 至 `ec3f2d0`，連到部署機（公網 `https://aiglasses.qzz.io/device/1/`）
- 進「管理員介面避障 AR」畫面卡「等待 YOLO 影像串流…」
- AR 畫面：NAV chip = `BLINDPATH_NAV`，FPS = 0
- server log：camera/audio WS 反覆連斷，**沒有任何 YOLO 推論輸出 log**
- 使用者陳述：「舊版 APP（5/10 前）沒這問題」

---

## 三條鏈架構

```
避障：
APP 相機 → /ws/camera → orchestrator (YOLO 推論) → encode JPEG
                                                         ↓
                       APP ar_screen ← viewerStream ← /ws/viewer

ASR：
APP mic → record stream → audio_service onChunk → /ws_audio → asr_core (GoogleASR)
                                                                    ↓
                          APP _onUiMessage ← /ws_ui ← ui_broadcast_partial/final

TTS：
server omni_client._call_tts (WaveNet→Gemini fallback) → broadcast_pcm16_realtime
                                                              ↓
            APP audioplayers UrlSource ← /stream.wav (20ms tick + 靜音 frame) ← stream_clients queue
```

---

## 找到的 Bug 清單

### 🔴 Bug 1：Camera WS 沒 keepalive、也沒 frame timeout

**檔案**：`app_main.py:1822`、`Android/lib/services/websocket_service.dart:16,40-53`

**症狀**：camera ws 在公網中介（Cloudflare Tunnel）100s idle timeout 殺連線時，**雙方都不知道**。viewer 因此無幀可收，AR 畫面停在「等待中」。

**根因**：
- server 端 `ws/camera` 是 `msg = await ws.receive()`，**沒 timeout**
- 對照組：`ws_audio` 有 `await asyncio.wait_for(..., timeout=15.0)`，`ws/viewer`、`ws_ui`、`ws_imu` 都有 30s PING，**唯獨 camera 沒有任何保活機制**
- APP 端 `_doConnectCamera` 也沒設 pingInterval、沒任何 keepalive
- `0a51a93` 註解明確說「不設 pingInterval：5 秒 ping 對 binary stream 太激進」—— 等於主動放棄 keepalive，但沒提供替代方案

**Log 對照**：
```
[CAMERA] ESP32 connected
[CAMERA] 已送出畫質/幀率限制指令（quality=15, fps=20）
（沒有任何 [NAVIGATION DEBUG] 帧:30 訊息 — 收幀數沒到 30 就斷）
[CAMERA] ESP32 disconnected
```

**修法建議**：
- **短期（server 端 1 行）**：`app_main.py:1822` 改為 `msg = await asyncio.wait_for(ws.receive(), timeout=30)`，例外 `asyncio.TimeoutError` 改為 break 加 log
- **中期（更穩）**：APP `_doConnectCamera` 改用 `IOWebSocketChannel.connect(url, pingInterval: Duration(seconds: 30))`，但需先驗證對 binary stream 不會 close code 1005（`0a51a93` 註解警告過此問題）

**影響範圍**：公網（Cloudflare 中介）必出，本地 server + adb reverse 不會。

---

### 🔴 Bug 2：Camera WS 斷線 → 整個 nav state reset（過度激進）

**檔案**：`app_main.py:2015-2031`

**症狀**：camera ws 短暫斷一下（即使網路抖動），server 端立刻 reset `blind_path_navigator`、`cross_street_navigator`、`orchestrator`。使用者得重新「開啟避障導航」。

**根因**：
```python
finally:
    esp32_camera_ws = None
    print("[CAMERA] ESP32 disconnected")
    if blind_path_navigator: blind_path_navigator.reset()
    if cross_street_navigator: cross_street_navigator.reset()
    if orchestrator:
        orchestrator.reset()
        print("[NAV MASTER] 统领器已重置")
```
無條件 reset，沒區分「短暫斷」vs「長時間斷」。

**Log 對照**：
```
[CAMERA] ESP32 disconnected
[TRAFFIC] 检测状态已重置
[TRAFFIC] 检测状态已重置
[NAV MASTER] 统领器已重置
```

**修法建議**：
- **短期**：加 grace period — 斷線後 10 秒內若 reconnect，**不 reset state**，僅在超過 10 秒才 reset
- **實作**：把 reset 邏輯移到延遲 task，新 connection 進來時 `task.cancel()`

**影響範圍**：與 Bug 1 疊加 → 公網中介每次斷線都導致 nav 重置 → 使用者體驗極差。

---

### 🔴 Bug 3：`sink.add(START)` 失敗但 Dart 不 throw（5/13 自承未解）

**檔案**：`Android/lib/services/websocket_service.dart:80-104`、`app_main.py:1429-1439`

**症狀**：APP 連 audio ws 後送 `START:BYPASS`，但 server 收不到。3 秒後 server 主動送 `RESTART` 給 client。

**根因**（`0a51a93` commit message 自承）：
> sink.add 在 dart 端不 throw 但實際失敗，APP 端的 onError/onDone 都不會觸發，唯一突破是 server 主動斷。

```dart
// websocket_service.dart _doConnectAudio
_audioWs = _connectWs(...);
final startCmd = _bypassWake ? 'START:BYPASS' : 'START';
_audioWs!.sink.add(startCmd);   // 若 ws 半關閉，這行不會 throw 但 server 收不到
_audioWsSub = _audioWs!.stream.listen(...);   // onError/onDone 也不觸發
```

**Log 對照**：
```
[AUDIO] client connected
[AUDIO] 未收到 START，送 RESTART 給 ESP32
```

**修法建議**：
- **短期（最確定）**：audio ws 連線後設一個 3 秒 timer，若沒收到 server 回 `OK:STARTED`（已存在於 `app_main.py:1529`），**主動 `disconnectAudio + connectAudio` 重試**
- **中期**：收到 `OK:STARTED` 才把 ws 標記為「真正可用」

**影響範圍**：每次 APP 重連 audio 都可能中槍，造成連續重連風暴。

---

### 🟠 Bug 4：`ec3f2d0` audio watchdog 只解 recorder 層，沒重啟 ws

**檔案**：`Android/lib/services/audio_service.dart:71-101`

**症狀**：watchdog 5 秒沒新 chunk 觸發後，重啟 recorder stream，但 audio ws 還是死的（Bug 3 的延伸）。新 chunk 還是送往死 ws，5 秒後 watchdog 又觸發 → 死循環。

**根因**：
```dart
Future<void> _restartMic(String reason) async {
  ...
  try { await _recordSub?.cancel(); } catch (_) {}
  try { await _recorder.stop(); } catch (_) {}
  await Future.delayed(const Duration(milliseconds: 200));
  await _startInternal();   // 只重啟 recorder，完全不碰 ws
  ...
}
```

`_onChunkCb` 是外部（`app_provider`）注入的 `(b) => _ws.sendAudioChunk(b)`，重啟 recorder 後新 chunk 還是往同一個（已死的）audio ws 送。

**修法建議**：
- **短期**：`_restartMic` 加 callback 通知外部 ws 也要重連。在 `app_provider` 注入時：watchdog 觸發 → `_ws.disconnectAudio() + _ws.connectAudio(...)`
- 或：watchdog 觸發第二次時 escalate 到 ws 重連
- 配合 Bug 3 的「等 OK:STARTED」機制更穩

**影響範圍**：Bug 3 觸發時，watchdog 不能救，必須靠 Bug 3 修法。

---

### 🟠 Bug 5：Audio / Camera 全域單例鎖競態

**檔案**：`app_main.py:1411-1413`（audio）、`1753-1755`（camera）

**症狀**：APP 重連時，若 server 端舊 `finally` 還沒跑完，新 ws 被拒（close code 1013）。

**根因**：
```python
if esp32_audio_ws is not None:
    await ws.close(code=1013); return
esp32_audio_ws = ws
```
單例鎖只在 `finally` 區塊清空，若 `stop_rec()` 或 `ws.close()` 卡住，鎖一直握。

**修法建議**：
- 加 timestamp：如果舊鎖超過 5 秒沒被清，新連線強制接手（先關舊的、再 accept 新的）
- 或用 `asyncio.Lock`，搭配 try/finally release 更乾淨

**影響範圍**：邊緣情境（網路抖動快速重連時）。

---

### 🟡 Bug 6：APP fps=10 vs server 期望 fps=20

**檔案**：`Android/lib/providers/app_provider.dart:578`、`app_main.py:1766`

**症狀**：viewer 更新頻率比 server 預期慢一半。

**根因**：
- server 連上後送 `SET:FPS=20`（這指令本來是給 ESP32 韌體解析，APP 沒解析器）
- APP `_startCamera`：`_camera.startStreaming(... fps: 10)`

**修法建議**：APP 端 fps 提到 20，或 server 端 `SET:FPS=10` 對齊。**不是 fatal**。

---

### 🟡 Bug 7：TTS audioplayers 重連只認 `PlayerState.completed`

**檔案**：`Android/lib/services/audio_service.dart:130-137`

**症狀**：若 audioplayers 因網路抖動進入 `disposed` 或其他失敗狀態，**不會觸發重連**。

**根因**：
```dart
if (_shouldPlayStream && state == PlayerState.completed) {
  _scheduleReconnect();
}
```
只認 completed，其他失敗狀態漏接。

**修法建議**：擴大條件 `completed || disposed` 都重連；或改為「pollPlayerState 每 5 秒一次，非 playing 且 `_shouldPlayStream` = true 就重連」。

**影響範圍**：server 端 stream.wav 持續送靜音 frame，正常情況很少進 completed。但中介抖動偶會中槍。

---

## 與已有修復的對齊

### `0a51a93`（5/13 已 push）改了什麼
**APP 端**：
- 新增全域 `AsrStatusOverlay`（黃 listening / 青藍 processing 雙狀態動畫）
- FINAL/PARTIAL 加 `startsWith('[')` filter，擋 server 廣播誤切 ASR 狀態
- `[AI]` 廣播時雖不切狀態但顯示去前綴文字在 chip 上
- listening 5s timeout、重連訊息、版本標記
- 移除 3s 麥克風延遲
- `WebSocketService` 改 `IOWebSocketChannel`（**行為等價，無實質改變**）

**Server 端**：
- `asr_core`: bypass + standby 模式也推 partial 給 UI
- `app_main`: ws_audio 連線分隔符 + **15s frame timeout 主動斷連**（部署機沒這段）
- `app_main`: 寬鬆 nav 判斷（含「導航/避障」+ 無停止字 = 啟動）
- `omni_client._call_tts`: WaveNet 優先，Gemini TTS 為後備

**自承未解**：本表 Bug 3（sink.add 失敗不 throw）

### `ec3f2d0`（5/13 本地未 push）改了什麼
**APP 端**：
- `audio_service.dart` 加 `_micWatchdog` 5s + `_restartMic`（**本表 Bug 4：只解 recorder 層**）
- `app_provider.dart` `[AI]` 廣播強切 processing + 重設 15s timer
- `AndroidManifest.xml` 加 `android:usesCleartextTraffic="true"`

**自動驗證已過**（emulator）：watchdog 觸發 log + stream.wav 連線 OK
**實機驗證未做**：清單 3 步（開啟避障導航 → 停止導航 → 現在幾點）

### 沒有人動過的（本次發現的新缺口）
- Bug 1：camera 沒 keepalive / timeout
- Bug 2：camera 斷就 reset 全部 nav state

---

## 修法優先級

### Priority 1 — 直接對應「等待中」症狀
- **Bug 1**：server `ws/camera` 加 30s receive timeout（10 分鐘改動）
- **Bug 2**：camera disconnect 改 graceful（grace period 10 秒）

### Priority 2 — ASR 穩定性（5/13 unsolved 的延伸）
- **Bug 3 + Bug 4 配套修**：audio ws 連線等 `OK:STARTED` + watchdog escalate 到 ws 重連

### Priority 3 — 邊緣 case / 觀感
- Bug 5：單例鎖 timeout
- Bug 6：fps 對齊
- Bug 7：TTS 重連條件擴大

---

## 實機測試前 sanity（部署機版）

部署機測試前必做決策：

### 1. 部署機 `git pull`（必做）
- 拉到 `origin/main` 會有：`0a51a93` server 修復（15s timeout / 寬鬆 nav / WaveNet TTS）、`1c86d9e` viewer 重連、`ec3f2d0` APP audio watchdog、本交接文件
- **拉了之後仍存在**：本表 Bug 1 / Bug 2 沒修、Bug 3 自承未解、Bug 4 watchdog 只解 recorder 層
- 拉之前先 `git fetch --tags` 確認 rollback tag 在（見下方「復原指令」段）

### 2. `ec3f2d0` push 狀態：✅ 已完成（2026-05-20）
- `ec3f2d0` + 本交接文件已 push 到 `origin/main`
- 復原 baseline tag `rollback-baseline-20260511` 已建並 push（指向 5/11 的 `017c7f5`）
- 部署機 `git pull` 即可拿到完整新版；測試失敗用下方「復原指令」段一鍵回退

### 3. 測試清單
見 memory `project_asr_repair_session_20260513.md` 的「使用者實機驗證清單」（3 步：開啟避障導航 → 停止導航 → 現在幾點）。

---

## 附錄

### 關鍵檔案行號速查
| Bug | 檔案 | 行號 |
|-----|------|------|
| 1 | `app_main.py` | 1822（`ws.receive`）|
| 1 | `Android/lib/services/websocket_service.dart` | 16（`_connectWs`）|
| 2 | `app_main.py` | 2015-2031（camera `finally`）|
| 3 | `Android/lib/services/websocket_service.dart` | 80-104（`_doConnectAudio`）|
| 3 | `app_main.py` | 1429-1439（`_auto_restart_if_no_start`）|
| 4 | `Android/lib/services/audio_service.dart` | 71-101（`_micWatchdog`/`_restartMic`）|
| 5 | `app_main.py` | 1411-1413, 1753-1755（單例鎖）|
| 6 | `Android/lib/providers/app_provider.dart` | 578（`_startCamera fps`）|
| 6 | `app_main.py` | 1766（`SET:FPS=20`）|
| 7 | `Android/lib/services/audio_service.dart` | 130-137（`PlayerState.completed`）|

### 相關 commit
- `0a51a93`（5/13）APP+server 連線修復 WIP — 已 push，自承核心 bug 未解
- `ec3f2d0`（5/13）APP 三 bug 修復 — 本地未 push，含 audio watchdog
- `1c86d9e`（~5/10）viewer WS 公網斷線不重連修復
- `017c7f5` 部署機目前停留處（5/11 拉的）

### 相關 memory（user-level，不入 git）
- `project_asr_repair_session_20260513.md` — 5/13 ASR 修復會話
- `feedback_viewer_accumulation_blackscreen.md` — viewer 累積黑屏（已修但 camera 沒受惠）
- `feedback_server_test_local_first.md` — server 改動先本地測試規則
- `feedback_final_prefix_broadcast_filter.md` — `[` 開頭一律擋的廣播 filter

---

## 復原指令（重要）

**部署機 5/11 拉的 commit (`017c7f5`) 已標記為 git tag**：

```
tag: rollback-baseline-20260511
```

### 部署機測試失敗時的復原流程

```bash
# 1. 先拉最新 tags
git fetch --tags

# 2. 強制復原到 5/11 baseline
git reset --hard rollback-baseline-20260511

# 3. 確認版本
git log -1 --oneline
# 應顯示：017c7f5 ...
```

⚠️ `git reset --hard` 會丟掉 working tree 內未 commit 的變更。若部署機 `.env`、`google_Speech_to_Text.json` 等 gitignore 檔案有變更，**不受 reset 影響**（不在版本控制內，安全）。但若 server 端有任何手改的 `.py`、新增的設定檔，先備份。

### 復原時機判斷

| 症狀 | 動作 |
|------|------|
| 部署機 pull 後 server 起不來（import error / syntax） | 立即復原 |
| 起得來但行為比舊版差（更頻繁斷線、錯誤指令） | 復原，回報症狀 |
| 與 5/11 持平或更好（同樣壞但沒新增壞點） | **不復原**，繼續 debug 本表 Bug 1/2 |
| 變好（避障 AR 出幀了！） | **不復原**，鎖定此版本
