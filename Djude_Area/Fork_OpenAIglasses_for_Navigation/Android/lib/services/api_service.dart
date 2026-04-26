// lib/services/api_service.dart
// HTTP API 呼叫（使用 dio）

import 'package:dio/dio.dart';
import '../core/constants.dart';

class ApiService {
  late final Dio _dio;
  final String host;
  final int    port;
  final bool   secure;
  final String? baseUrl;

  ApiService({required this.host, required this.port, this.secure = false, this.baseUrl}) {
    _dio = Dio(BaseOptions(
      // Dio v5 URL 合併規則：baseUrl 結尾補 /，request path 開頭的 / 被 strip，
      // 再直接字串拼接。baseUrl 若已含 /device/1，Dio 會自動拼成 /device/1/api/xxx，
      // 不需要額外的 _pathPrefix 補綴（補了反而會變成 /device/1/device/1/api/xxx）。
      baseUrl:        AppConstants.httpBase(host, port, secure: secure, baseUrl: baseUrl),
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 15),
    ));
  }

  // ── 健康檢查（用於測試連線）──────────────────────────────────────────────
  Future<bool> healthCheck() async {
    final resp = await _dio.get('/api/health');
    return resp.statusCode == 200;
  }

  // ── 文件閱讀 ─────────────────────────────────────────────────────────────
  Future<Map<String, dynamic>> readDocument(String imageBase64) async {
    final resp = await _dio.post(
      '/api/read_document',
      data: {'image_b64': imageBase64},
      options: Options(receiveTimeout: const Duration(seconds: 90)),
    );
    final data = resp.data;
    return data is Map<String, dynamic> ? data : {};
  }

  Future<Map<String, dynamic>> explainDocument(String text, String question) async {
    final resp = await _dio.post(
      '/api/explain_document',
      data: {'text': text, 'question': question},
      options: Options(receiveTimeout: const Duration(seconds: 60)),
    );
    final data = resp.data;
    return data is Map<String, dynamic> ? data : {};
  }

  // ── 導航控制 ─────────────────────────────────────────────────────────────
  Future<Map<String, dynamic>> navState() async {
    final resp = await _dio.get('/api/nav/state');
    final data = resp.data;
    return data is Map<String, dynamic> ? data : {};
  }

  Future<void> navBlindpath()    => _dio.post('/api/nav/blindpath');
  Future<void> navCrossing()     => _dio.post('/api/nav/crossing');
  Future<void> navTrafficLight() => _dio.post('/api/nav/traffic_light');
  Future<void> navStop()         => _dio.post('/api/nav/stop');

  Future<void> navItemSearch(String itemName, {String positionMode = 'clock'}) async {
    await _dio.post('/api/nav/item_search',
        data: {'item_name': itemName, 'position_mode': positionMode});
  }

  Future<void> setPositionMode(String mode) async {
    await _dio.post('/api/settings/position_mode', data: {'mode': mode});
  }

  // ── 伺服器 Debug 狀態 ─────────────────────────────────────────────────────
  Future<Map<String, dynamic>> debugStatus() async {
    final resp = await _dio.get('/api/debug_status');
    final data = resp.data;
    return data is Map<String, dynamic> ? data : {};
  }

}
