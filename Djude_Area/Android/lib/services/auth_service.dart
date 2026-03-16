// lib/services/auth_service.dart
// JWT 本地儲存與讀取

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../core/constants.dart';

class AuthService {
  static const _storage = FlutterSecureStorage();

  // ── 儲存登入資訊 ─────────────────────────────────────────────────────────
  static Future<void> saveSession({
    required String token,
    required String username,
    required String role,
    required int    userId,
  }) async {
    await Future.wait([
      _storage.write(key: AppConstants.keyToken,    value: token),
      _storage.write(key: AppConstants.keyUsername, value: username),
      _storage.write(key: AppConstants.keyRole,     value: role),
      _storage.write(key: AppConstants.keyUserId,   value: userId.toString()),
    ]);
  }

  // ── 讀取 ─────────────────────────────────────────────────────────────────
  static Future<String?> getToken()    => _storage.read(key: AppConstants.keyToken);
  static Future<String?> getUsername() => _storage.read(key: AppConstants.keyUsername);
  static Future<String?> getRole()     => _storage.read(key: AppConstants.keyRole);
  static Future<int?> getUserId() async {
    final s = await _storage.read(key: AppConstants.keyUserId);
    return s != null ? int.tryParse(s) : null;
  }

  // ── 登出（清除）─────────────────────────────────────────────────────────
  static Future<void> clearSession() async {
    await Future.wait([
      _storage.delete(key: AppConstants.keyToken),
      _storage.delete(key: AppConstants.keyUsername),
      _storage.delete(key: AppConstants.keyRole),
      _storage.delete(key: AppConstants.keyUserId),
    ]);
  }

  // ── 是否有有效 session ───────────────────────────────────────────────────
  static Future<bool> hasSession() async {
    final token = await getToken();
    return token != null && token.isNotEmpty;
  }
}
