<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# static

## Purpose
Web 前端靜態資源，包含 JavaScript 模組、CSS 樣式和 3D 模型檔案，用於監控儀表板和 IMU 可視化。

## Key Files

| File | Description |
|------|-------------|
| `main.js` | 主 JavaScript 邏輯 (WebSocket 連接、UI 更新、事件處理) |
| `vision.js` | 視覺流處理 (WebSocket 接收視頻幀、Canvas 渲染、FPS 計算) |
| `visualizer.js` | IMU 3D 可視化 (Three.js 實現，接收 IMU 數據，實時渲染設備姿態) |
| `vision_renderer.js` | 渲染器模組 |
| `vision.css` | 樣式表 |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `models/` | 3D 模型檔案 (IMU 可視化用) |

## For AI Agents

### Working In This Directory
- WebSocket 連接:
  - `/ws/viewer` - 接收標註後的 JPEG 幀
  - `/ws` - 接收 IMU 數據
- Three.js 用於 3D 渲染 IMU 姿態

### Testing Requirements
- 瀏覽器開發者工具檢查 WebSocket 連接狀態
- Console 檢查 FPS 和延遲日誌

### Common Patterns
- Canvas 渲染視頻幀
- WebSocket 事件驅動更新
- Three.js 動態燈光效果

## Dependencies

### External
- Three.js - 3D 渲染庫

<!-- MANUAL: -->
