// lib/services/website_api_service.dart
// 連 Django Website 的 HTTP client，群眾外包路口停等資料專用。
//
// baseUrl 由 AppConstants.resolveWebsiteUrl() 從現有 ServerSettings 推導：
//   - AI server 走 https/Cloudflared → 用 defaultWebsitePublicUrl
//   - AI server 走 區網 IP            → 同 host 換 port 8888

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import '../core/constants.dart';

class IntersectionInfo {
  final String gridId;
  final double? avgDurationSec; // 可能為 null（樣本不足時）
  final int sampleSize;
  final int activeCount;

  const IntersectionInfo({
    required this.gridId,
    required this.avgDurationSec,
    required this.sampleSize,
    required this.activeCount,
  });

  factory IntersectionInfo.fromJson(Map<String, dynamic> j) => IntersectionInfo(
        gridId: j['grid_id'] as String? ?? '',
        avgDurationSec: (j['avg_duration_sec'] as num?)?.toDouble(),
        sampleSize: (j['sample_size'] as num?)?.toInt() ?? 0,
        activeCount: (j['active_count'] as num?)?.toInt() ?? 0,
      );
}

class WebsiteApiService {
  late final Dio _dio;
  final String baseUrl;

  WebsiteApiService({required this.baseUrl}) {
    _dio = Dio(BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 5),
      receiveTimeout: const Duration(seconds: 5),
      headers: {'Content-Type': 'application/json'},
    ));
  }

  /// 上傳一筆停等事件（停等結束時呼叫）
  Future<bool> reportWait({
    required double lat,
    required double lng,
    required int durationSec,
    required String deviceHash,
    required DateTime startedAt,
    required DateTime endedAt,
  }) async {
    try {
      final resp = await _dio.post(
        AppConstants.pathIntersectionWait,
        data: {
          'lat': _round5(lat),
          'lng': _round5(lng),
          'duration_sec': durationSec,
          'device_hash': deviceHash,
          'started_at': startedAt.toUtc().toIso8601String(),
          'ended_at':   endedAt.toUtc().toIso8601String(),
        },
      );
      return resp.statusCode == 200 && (resp.data?['ok'] == true);
    } catch (e) {
      debugPrint('[WebsiteAPI] reportWait 失敗: $e');
      return false;
    }
  }

  /// Heartbeat：停等中每 N 秒呼叫一次，標記裝置仍在這格等待
  Future<bool> heartbeat({
    required double lat,
    required double lng,
    required String deviceHash,
  }) async {
    try {
      final resp = await _dio.post(
        AppConstants.pathIntersectionHeartbeat,
        data: {
          'lat': _round5(lat),
          'lng': _round5(lng),
          'device_hash': deviceHash,
        },
      );
      return resp.statusCode == 200 && (resp.data?['ok'] == true);
    } catch (e) {
      debugPrint('[WebsiteAPI] heartbeat 失敗: $e');
      return false;
    }
  }

  /// 查詢當前位置所在路口的彙整資訊
  Future<IntersectionInfo?> queryInfo({
    required double lat,
    required double lng,
  }) async {
    try {
      final resp = await _dio.get(
        AppConstants.pathIntersectionInfo,
        queryParameters: {'lat': _round5(lat), 'lng': _round5(lng)},
      );
      if (resp.statusCode != 200 || resp.data?['ok'] != true) return null;
      return IntersectionInfo.fromJson(resp.data as Map<String, dynamic>);
    } catch (e) {
      debugPrint('[WebsiteAPI] queryInfo 失敗: $e');
      return null;
    }
  }

  // 隱私 L2：座標上傳前 round 到 5 位小數（11m 精度）
  double _round5(double v) => (v * 100000).round() / 100000.0;
}
