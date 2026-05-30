// lib/services/places_service.dart
// 儲存地點本機資料庫（SQLite）
// 用於 GPS 導航：使用者可儲存常用目的地，免去每次手動輸入

import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart' as p;

class PlacesService {
  static Database? _db;

  static Future<Database> _getDb() async {
    if (_db != null) return _db!;
    final dbPath = await getDatabasesPath();
    _db = await openDatabase(
      p.join(dbPath, 'places.db'),
      version: 1,
      onCreate: (db, _) => db.execute('''
        CREATE TABLE places (
          id        INTEGER PRIMARY KEY AUTOINCREMENT,
          name      TEXT NOT NULL,
          address   TEXT NOT NULL DEFAULT '',
          latitude  REAL NOT NULL DEFAULT 0,
          longitude REAL NOT NULL DEFAULT 0,
          category  TEXT NOT NULL DEFAULT 'other',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
      '''),
    );
    return _db!;
  }

  /// 取得所有儲存地點（依名稱排序）
  static Future<List<Map<String, dynamic>>> listPlaces() async {
    final db = await _getDb();
    return db.query('places', orderBy: 'name');
  }

  /// 新增地點
  static Future<int> addPlace({
    required String name,
    String address = '',
    double latitude = 0,
    double longitude = 0,
    String category = 'other',
  }) async {
    final db = await _getDb();
    return db.insert('places', {
      'name': name,
      'address': address,
      'latitude': latitude,
      'longitude': longitude,
      'category': category,
    });
  }

  /// 更新地點
  static Future<void> updatePlace(int id, {
    required String name,
    String address = '',
    double latitude = 0,
    double longitude = 0,
    String category = 'other',
  }) async {
    final db = await _getDb();
    await db.update(
      'places',
      {
        'name': name,
        'address': address,
        'latitude': latitude,
        'longitude': longitude,
        'category': category,
      },
      where: 'id = ?',
      whereArgs: [id],
    );
  }

  /// 刪除地點
  static Future<void> deletePlace(int id) async {
    final db = await _getDb();
    await db.delete('places', where: 'id = ?', whereArgs: [id]);
  }
}
