<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# templates

## Purpose
HTML 模板目錄，包含 Web 監控界面的主頁面模板。

## Key Files

| File | Description |
|------|-------------|
| `index.html` | Web 監控界面主頁面 (視頻流顯示、狀態面板、IMU 3D 可視化、語音識別結果) |

## For AI Agents

### Working In This Directory
- 使用 Jinja2 模板語法 (如有動態內容)
- 主要為靜態 HTML，引用 `../static/` 下的資源

### Main UI Sections
1. 視頻流顯示區
2. 狀態面板 (當前模式、檢測結果)
3. IMU 3D 可視化區
4. 語音識別結果顯示

## Dependencies

### Internal
- `../static/` - JavaScript 和 CSS 資源

<!-- MANUAL: -->
