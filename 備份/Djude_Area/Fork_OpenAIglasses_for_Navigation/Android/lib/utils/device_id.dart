// lib/utils/device_id.dart
// 匿名裝置識別碼：首次啟動時生成 64-char 隨機 hex，存 SharedPreferences。
// 用途：群眾外包路口停等資料的去識別化裝置標記（隱私 L2）。
// 沒有用 SHA-256：本來就是隨機字串，伺服器從未拿到「原始 device id」可逆推。

import 'dart:math';
import 'package:shared_preferences/shared_preferences.dart';

class DeviceId {
  static const String _key = 'anonymous_device_hash';
  static String? _cached;

  /// 取得（或首次啟動時生成）匿名裝置識別碼，64-char hex string。
  static Future<String> get() async {
    if (_cached != null) return _cached!;
    final sp = await SharedPreferences.getInstance();
    var id = sp.getString(_key);
    if (id == null || id.length != 64) {
      id = _randomHex64();
      await sp.setString(_key, id);
    }
    _cached = id;
    return id;
  }

  static String _randomHex64() {
    final r = Random.secure();
    final bytes = List<int>.generate(32, (_) => r.nextInt(256));
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  }
}
