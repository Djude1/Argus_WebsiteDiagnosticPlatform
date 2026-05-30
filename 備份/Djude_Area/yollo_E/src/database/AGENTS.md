<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-16 | Updated: 2026-03-16 -->

# database

## Purpose
SQLite 資料庫管理模組，記錄偵測到的物品資訊並提供查詢介面。

## Key Files

| File | Description |
|------|-------------|
| `db_manager.py` | 資料庫管理器，負責 SQLite 連線和基本 CRUD 操作 |
| `item_logger.py` | 物品記錄器，處理偵測結果寫入資料庫 |
| `models.py` | SQLAlchemy ORM 模型定義 |
| `__init__.py` | 模組匯出 |

## For AI Agents

### Working In This Directory
- 使用 SQLAlchemy ORM 進行資料庫操作
- SQLite 資料庫路徑：`data/database/items.db`
- 支援 session（會話）概念，每段偵測為一個會話

### Database Schema

**items 表 (物品記錄)**
| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER | 主鍵 |
| name | TEXT | 物品名稱（中文）|
| name_en | TEXT | 英文名稱 |
| category | TEXT | 分類 |
| confidence | REAL | 信心度 |
| class_id | INTEGER | YOLO 類別 ID |
| first_seen | DATETIME | 首次辨識時間 |
| last_seen | DATETIME | 最後辨識時間 |
| detection_count | INTEGER | 辨識次數 |

**sessions 表 (偵測會話)**
| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER | 主鍵 |
| source | TEXT | 影像來源 (esp32/webcam) |
| source_ip | TEXT | 來源 IP |
| start_time | DATETIME | 開始時間 |
| end_time | DATETIME | 結束時間 |
| total_frames | INTEGER | 總幀數 |
| avg_fps | REAL | 平均 FPS |

### 使用範例

```python
from src.database.db_manager import DatabaseManager

db = DatabaseManager("data/database/items.db")

# 取得最近 50 筆記錄
recent = db.get_recent_items(50)

# 取得最常出現的物品
frequent = db.get_frequent_items(20)

# 取得統計資訊
stats = db.get_statistics()
```

## Dependencies

### Internal
- `src/config.py` - 取得資料庫路徑

### External
- sqlalchemy - ORM 框架
- sqlite3 - 內建資料庫

