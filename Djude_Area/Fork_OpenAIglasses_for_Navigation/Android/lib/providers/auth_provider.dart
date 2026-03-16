// lib/providers/auth_provider.dart
// 管理登入狀態
// - guest（前台免登入，所有導航功能可用）
// - admin（後台管理員登入）

import 'package:flutter/material.dart';
import '../services/auth_service.dart';
import '../services/api_service.dart';

enum AuthStatus { unknown, guest, loggedIn }

class AuthProvider extends ChangeNotifier {
  AuthStatus _status   = AuthStatus.unknown;
  String     _username = '';
  String     _role     = 'user';
  int        _userId   = -1;

  AuthStatus get status   => _status;
  String     get username => _username;
  String     get role     => _role;
  int        get userId   => _userId;

  bool get isAdmin    => _status == AuthStatus.loggedIn && _role == 'admin';
  bool get isOperator =>
      _status == AuthStatus.loggedIn &&
      (_role == 'admin' || _role == 'operator');
  bool get isLoggedIn => _status == AuthStatus.loggedIn;

  /// 初始化：預設為 guest，若有儲存的 token 則嘗試恢復 admin session
  Future<void> init() async {
    final hasSession = await AuthService.hasSession();
    if (hasSession) {
      _username = (await AuthService.getUsername()) ?? '';
      _role     = (await AuthService.getRole())     ?? 'user';
      _userId   = (await AuthService.getUserId())   ?? -1;
      _status   = AuthStatus.loggedIn;
    } else {
      // 前台免登入，預設 guest 模式
      _status = AuthStatus.guest;
    }
    notifyListeners();
  }

  /// 後台管理員登入
  Future<String?> loginAdmin(String username, String password,
      ApiService api) async {
    try {
      final result = await api.login(username, password);
      final role = result['role'] as String;
      if (role != 'admin' && role != 'operator') {
        return '此帳號無後台管理權限';
      }
      await AuthService.saveSession(
        token:    result['token']    as String,
        username: result['username'] as String,
        role:     role,
        userId:   result['user_id'] as int,
      );
      _username = result['username'] as String;
      _role     = role;
      _userId   = result['user_id'] as int;
      _status   = AuthStatus.loggedIn;
      notifyListeners();
      return null; // 成功
    } catch (e) {
      return '帳號或密碼錯誤';
    }
  }

  /// 登出後台（回到 guest 模式，不影響前台使用）
  Future<void> logoutAdmin() async {
    await AuthService.clearSession();
    _username = '';
    _role     = 'user';
    _userId   = -1;
    _status   = AuthStatus.guest;
    notifyListeners();
  }
}
