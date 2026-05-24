// lib/services/intersection_wait_service.dart
// 群眾外包路口停等資料收集：偵測使用者靜止 → 計時 → 上傳 + 查詢即時資訊。
//
// 設計原則：
// - 與 gps_navigation_service 完全獨立，各自訂閱 Geolocator
// - 「靜止」用 speed 連續 N 秒低於閾值來判斷（避免單點抖動誤判）
// - 隱私 L2：上傳前座標 round 到 5 位、device_hash 為匿名 64-hex

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

import '../utils/device_id.dart';
import 'website_api_service.dart';

class IntersectionWaitStatus {
  final bool isWaiting;            // 是否正在停等中
  final int currentWaitSec;        // 當前停等已累積秒數
  final IntersectionInfo? info;    // 該路口的彙整資訊（查詢結果）
  final int? lastCompletedWaitSec; // 上一次完成的停等秒數（移動後）

  const IntersectionWaitStatus({
    this.isWaiting = false,
    this.currentWaitSec = 0,
    this.info,
    this.lastCompletedWaitSec,
  });
}

typedef IntersectionWaitCallback = void Function(IntersectionWaitStatus status);

class IntersectionWaitService {
  IntersectionWaitService._();
  static final instance = IntersectionWaitService._();

  /// 反應式狀態通知器：UI 可用 ValueListenableBuilder 訂閱
  final ValueNotifier<IntersectionWaitStatus?> statusNotifier = ValueNotifier(null);

  // ── 閾值參數 ────────────────────────────────────────────────────────────
  static const double _stillSpeedMps = 0.5;       // 速度低於此值視為靜止
  static const int    _enterWaitDelaySec = 3;     // 連續靜止 N 秒才算「開始停等」
  static const int    _minReportSec = 3;          // 停等少於此秒數不上傳（雜訊）
  static const int    _heartbeatIntervalSec = 10; // heartbeat 間隔
  static const int    _queryIntervalSec = 10;     // info 查詢間隔

  // ── 狀態 ────────────────────────────────────────────────────────────────
  bool _enabled = false;
  StreamSubscription<Position>? _positionSub;
  Timer? _tickTimer;

  WebsiteApiService? _api;
  String? _deviceHash;

  DateTime? _stillSince;     // 連續靜止起點（speed < 閾值）
  DateTime? _waitStart;      // 真正停等開始時刻（_stillSince 持續 >= _enterWaitDelaySec）
  Position? _waitStartPosition; // 停等開始位置（上傳/heartbeat 都用這個算 grid_id，避免邊界跳格）
  Position?  _latestPosition;
  DateTime? _lastHeartbeatAt;
  DateTime? _lastQueryAt;
  IntersectionInfo? _latestInfo;
  int? _lastCompletedWaitSec;

  IntersectionWaitCallback? _onStatus;

  bool get isEnabled => _enabled;

  /// 啟動服務
  /// [websiteBaseUrl]：Django 的 base URL，由 AppConstants.resolveWebsiteUrl 推導
  Future<void> start({
    required String websiteBaseUrl,
    required IntersectionWaitCallback onStatus,
  }) async {
    if (_enabled) {
      debugPrint('[IntersectionWait] 已在運行，忽略 start');
      return;
    }
    _api = WebsiteApiService(baseUrl: websiteBaseUrl);
    _deviceHash = await DeviceId.get();
    _onStatus = onStatus;
    _enabled = true;

    // distanceFilter: 0 → 靜止時也有更新（GPS 自然抖動會觸發）
    // accuracy: medium → 路口級別 30m 方格不需要 high，省電
    _positionSub = Geolocator.getPositionStream(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.medium,
        distanceFilter: 0,
      ),
    ).listen(_onPosition, onError: (e) {
      debugPrint('[IntersectionWait] 位置串流錯誤: $e');
    });

    // 每秒 tick：累計停等秒數 + 觸發 heartbeat / query 排程
    _tickTimer = Timer.periodic(const Duration(seconds: 1), (_) => _tick());

    debugPrint('[IntersectionWait] 服務啟動，baseUrl=$websiteBaseUrl');
  }

  /// 停止服務（不會主動上傳尚未結束的停等，避免短時間 toggle 誤觸）
  Future<void> stop() async {
    _positionSub?.cancel();
    _positionSub = null;
    _tickTimer?.cancel();
    _tickTimer = null;
    _enabled = false;
    _stillSince = null;
    _waitStart = null;
    _waitStartPosition = null;
    _latestPosition = null;
    _lastHeartbeatAt = null;
    _lastQueryAt = null;
    _latestInfo = null;
    debugPrint('[IntersectionWait] 服務已停止');
  }

  // ── 位置更新：判斷靜止/移動轉換 ────────────────────────────────────────
  void _onPosition(Position p) {
    _latestPosition = p;
    final speed = p.speed.isNaN ? 0.0 : p.speed; // 起步時可能為 NaN
    final now = DateTime.now();

    if (speed < _stillSpeedMps) {
      // 靜止
      _stillSince ??= now;
      // 連續靜止超過閾值 → 進入「停等中」
      if (_waitStart == null &&
          now.difference(_stillSince!).inSeconds >= _enterWaitDelaySec) {
        _waitStart = _stillSince;
        _waitStartPosition = p; // 鎖定停等位置，後續 heartbeat / report 都用這個 grid_id
        debugPrint('[IntersectionWait] 進入停等：lat=${p.latitude}, lng=${p.longitude}');
      }
    } else {
      // 開始移動：若先前在停等，結算並上傳
      if (_waitStart != null) {
        _completeWait();
      }
      _stillSince = null;
      _waitStart = null;
      _waitStartPosition = null;
    }
  }

  // ── 每秒 tick：累積時間 + 觸發 heartbeat/query ─────────────────────────
  void _tick() {
    if (!_enabled) return;
    final p = _latestPosition;
    if (p == null) return;
    final now = DateTime.now();

    if (_waitStart != null) {
      // 停等中：heartbeat + 定期查詢路口資訊
      // 用「停等起始位置」算 grid_id，與結算上傳一致，避免邊界抖動跨格
      final anchor = _waitStartPosition ?? p;
      final waitSec = now.difference(_waitStart!).inSeconds;
      _maybeHeartbeat(anchor, now);
      _maybeQueryInfo(anchor, now);
      _emitStatus(isWaiting: true, currentWaitSec: waitSec);
    } else {
      _emitStatus(isWaiting: false, currentWaitSec: 0);
    }
  }

  void _maybeHeartbeat(Position p, DateTime now) {
    if (_api == null || _deviceHash == null) return;
    if (_lastHeartbeatAt != null &&
        now.difference(_lastHeartbeatAt!).inSeconds < _heartbeatIntervalSec) {
      return;
    }
    _lastHeartbeatAt = now;
    _api!.heartbeat(
      lat: p.latitude,
      lng: p.longitude,
      deviceHash: _deviceHash!,
    );
  }

  void _maybeQueryInfo(Position p, DateTime now) {
    if (_api == null) return;
    if (_lastQueryAt != null &&
        now.difference(_lastQueryAt!).inSeconds < _queryIntervalSec) {
      return;
    }
    _lastQueryAt = now;
    _api!.queryInfo(lat: p.latitude, lng: p.longitude).then((info) {
      if (info != null) {
        _latestInfo = info;
        // 立即推送一次，讓 UI 顯示最新平均/併發
        if (_waitStart != null) {
          final waitSec = DateTime.now().difference(_waitStart!).inSeconds;
          _emitStatus(isWaiting: true, currentWaitSec: waitSec);
        }
      }
    });
  }

  // ── 結算停等 ────────────────────────────────────────────────────────────
  void _completeWait() {
    if (_api == null || _deviceHash == null || _waitStart == null) return;
    // 用「停等起始位置」上傳，與 heartbeat 同一 grid_id，server 才能正確 delete ActiveWaiter
    final anchor = _waitStartPosition;
    if (anchor == null) {
      debugPrint('[IntersectionWait] _waitStartPosition 為 null，跳過上傳');
      return;
    }
    final endedAt = DateTime.now();
    final duration = endedAt.difference(_waitStart!).inSeconds;
    if (duration < _minReportSec) {
      debugPrint('[IntersectionWait] 停等過短（$duration s），不上傳');
      return;
    }
    debugPrint('[IntersectionWait] 結算停等：$duration s，上傳中…');
    _api!.reportWait(
      lat: anchor.latitude,
      lng: anchor.longitude,
      durationSec: duration,
      deviceHash: _deviceHash!,
      startedAt: _waitStart!,
      endedAt: endedAt,
    );
    _lastCompletedWaitSec = duration;
    _emitStatus(isWaiting: false, currentWaitSec: 0);
  }

  void _emitStatus({required bool isWaiting, required int currentWaitSec}) {
    final s = IntersectionWaitStatus(
      isWaiting: isWaiting,
      currentWaitSec: currentWaitSec,
      info: _latestInfo,
      lastCompletedWaitSec: _lastCompletedWaitSec,
    );
    statusNotifier.value = s;
    _onStatus?.call(s);
  }
}
