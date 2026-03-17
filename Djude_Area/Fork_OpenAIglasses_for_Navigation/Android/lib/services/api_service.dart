// lib/services/api_service.dart
// HTTP API 呼叫（使用 dio）

import 'package:dio/dio.dart';
import '../core/constants.dart';
import 'auth_service.dart';

class ApiService {
  late final Dio _dio;
  final String host;
  final int    port;
  final bool   secure;
  final String? baseUrl;

  ApiService({required this.host, required this.port, this.secure = false, this.baseUrl}) {
    _dio = Dio(BaseOptions(
      baseUrl:        AppConstants.httpBase(host, port, secure: secure, baseUrl: baseUrl),
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 15),
    ));
    // 自動附加 Bearer token
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await AuthService.getToken();
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        handler.next(options);
      },
    ));
  }

  // ── 健康檢查（不需 token，用於測試連線）──────────────────────────────────
  Future<bool> healthCheck() async {
    final resp = await _dio.get('/api/health');
    return resp.statusCode == 200;
  }

  // ── 認證 ─────────────────────────────────────────────────────────────────
  Future<Map<String, dynamic>> login(String username, String password) async {
    final resp = await _dio.post('/api/login',
        data: {'username': username, 'password': password});
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getMe() async {
    final resp = await _dio.get('/api/me');
    return resp.data as Map<String, dynamic>;
  }

  Future<void> changePassword(String oldPw, String newPw) async {
    await _dio.post('/api/me/password',
        data: {'old_password': oldPw, 'new_password': newPw});
  }

  // ── 使用者管理（Admin）──────────────────────────────────────────────────
  Future<List<dynamic>> listUsers() async {
    final resp = await _dio.get('/api/users');
    return resp.data as List<dynamic>;
  }

  Future<Map<String, dynamic>> createUser(
      String username, String password, String role) async {
    final resp = await _dio.post('/api/users',
        data: {'username': username, 'password': password, 'role': role});
    return resp.data as Map<String, dynamic>;
  }

  Future<void> updateUser(int id,
      {String? role, bool? enabled, String? password}) async {
    await _dio.put('/api/users/$id', data: {
      if (role     != null) 'role':     role,
      if (enabled  != null) 'enabled':  enabled,
      if (password != null) 'password': password,
    });
  }

  Future<void> deleteUser(int id) async {
    await _dio.delete('/api/users/$id');
  }

  // ── 緊急連絡人 ───────────────────────────────────────────────────────────
  Future<List<dynamic>> listContacts() async {
    final resp = await _dio.get('/api/contacts');
    return resp.data as List<dynamic>;
  }

  Future<void> addContact(String name, String phone) async {
    await _dio.post('/api/contacts', data: {'name': name, 'phone': phone});
  }

  Future<void> updateContact(int id, String name, String phone) async {
    await _dio.put('/api/contacts/$id', data: {'name': name, 'phone': phone});
  }

  Future<void> deleteContact(int id) async {
    await _dio.delete('/api/contacts/$id');
  }

  // ── 導航控制 ─────────────────────────────────────────────────────────────
  Future<Map<String, dynamic>> navState() async {
    final resp = await _dio.get('/api/nav/state');
    return resp.data as Map<String, dynamic>;
  }

  Future<void> navBlindpath()    => _dio.post('/api/nav/blindpath');
  Future<void> navCrossing()     => _dio.post('/api/nav/crossing');
  Future<void> navTrafficLight() => _dio.post('/api/nav/traffic_light');
  Future<void> navStop()         => _dio.post('/api/nav/stop');

  Future<void> navItemSearch(String itemName) async {
    await _dio.post('/api/nav/item_search',
        data: {'item_name': itemName});
  }
}
