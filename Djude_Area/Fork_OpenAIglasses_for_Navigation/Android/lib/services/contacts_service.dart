// lib/services/contacts_service.dart
// 緊急連絡人本機儲存（SQLite），不需伺服器登入

import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart' as p;

class ContactsService {
  static Database? _db;

  static Future<Database> _getDb() async {
    if (_db != null) return _db!;
    final dbPath = await getDatabasesPath();
    _db = await openDatabase(
      p.join(dbPath, 'contacts.db'),
      version: 1,
      onCreate: (db, _) => db.execute('''
        CREATE TABLE contacts (
          id    INTEGER PRIMARY KEY AUTOINCREMENT,
          name  TEXT NOT NULL,
          phone TEXT NOT NULL
        )
      '''),
    );
    return _db!;
  }

  static Future<List<Map<String, dynamic>>> listContacts() async {
    final db = await _getDb();
    return db.query('contacts', orderBy: 'name');
  }

  static Future<int> addContact(String name, String phone) async {
    final db = await _getDb();
    return db.insert('contacts', {'name': name, 'phone': phone});
  }

  static Future<void> updateContact(int id, String name, String phone) async {
    final db = await _getDb();
    await db.update(
      'contacts',
      {'name': name, 'phone': phone},
      where: 'id = ?',
      whereArgs: [id],
    );
  }

  static Future<void> deleteContact(int id) async {
    final db = await _getDb();
    await db.delete('contacts', where: 'id = ?', whereArgs: [id]);
  }
}
