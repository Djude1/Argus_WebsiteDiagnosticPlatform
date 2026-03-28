// lib/services/imu_service.dart
// 手機 IMU（加速度計 + 陀螺儀）
// 功能一：定期將 IMU 資料透過 WebSocket 上行給伺服器
// 功能二：獨立偵測劇烈撞擊（跌倒 / 車禍）並回呼通知

import 'dart:async';
import 'dart:math';
import 'package:sensors_plus/sensors_plus.dart';

typedef ImuCallback    = void Function(Map<String, dynamic> data);
// magnitude：加速度合力（m/s²），除以 9.8 可換算成 G 值
typedef ImpactCallback = void Function(double magnitude);

class ImuService {
  StreamSubscription? _accelSub;
  StreamSubscription? _gyroSub;
  Timer?              _sendTimer;

  double _ax = 0, _ay = 0, _az = 0;
  double _gx = 0, _gy = 0, _gz = 0;

  // ── 撞擊偵測參數（可透過 configure() 按裝置調整）────────────────────────
  /// 觸發閾值：加速度合力超過此值（m/s²）才算撞擊
  /// 9.8 = 1G（靜止），預設 30 ≈ 3G 以上才觸發，避免一般走路誤判
  double _impactThreshold = 30.0;

  /// 觸發後的冷卻時間，避免連續誤觸
  Duration _cooldown = const Duration(seconds: 30);

  DateTime?       _lastImpact;
  ImpactCallback? _onImpact;

  /// 從伺服器取得的個人化設定套用到此服務
  void configure({double? impactThreshold, int? cooldownSeconds}) {
    if (impactThreshold != null) _impactThreshold = impactThreshold;
    if (cooldownSeconds != null) _cooldown = Duration(seconds: cooldownSeconds);
  }

  // ── 啟動 IMU 資料上行 ──────────────────────────────────────────────────────
  void start({required ImuCallback onData, int intervalMs = 100}) {
    _accelSub = accelerometerEventStream().listen((e) {
      _ax = e.x; _ay = e.y; _az = e.z;
      _checkImpact();
    });
    _gyroSub = gyroscopeEventStream().listen((e) {
      _gx = e.x; _gy = e.y; _gz = e.z;
    });
    _sendTimer = Timer.periodic(Duration(milliseconds: intervalMs), (_) {
      onData({
        'ax': _ax, 'ay': _ay, 'az': _az,
        'gx': _gx, 'gy': _gy, 'gz': _gz,
      });
    });
  }

  // ── 啟動撞擊偵測（獨立，不需要啟動資料上行）─────────────────────────────
  void startImpactDetection({required ImpactCallback onImpact}) {
    _onImpact = onImpact;
    // 若 start() 已建立 _accelSub，撞擊偵測直接共用（_checkImpact 在 listen 裡已呼叫）
    // 若尚未建立，才獨立建立一個
    if (_accelSub == null) {
      _accelSub = accelerometerEventStream().listen((e) {
        _ax = e.x; _ay = e.y; _az = e.z;
        _checkImpact();
      });
    }
    // 若 start() 已建立了 _accelSub 但沒有呼叫 _checkImpact，
    // 需要重新訂閱以確保偵測邏輯在裡面（重啟訂閱）
    else if (_sendTimer != null) {
      // start() 在跑：重新建立訂閱，加入 _checkImpact
      _accelSub?.cancel();
      _accelSub = accelerometerEventStream().listen((e) {
        _ax = e.x; _ay = e.y; _az = e.z;
        _checkImpact();
      });
    }
  }

  // ── 重啟撞擊偵測（從背景返回前台時呼叫，重建感測器訂閱）─────────────────
  void restartImpactDetection({required ImpactCallback onImpact}) {
    _onImpact = onImpact;
    // 取消舊訂閱，重新建立，確保感測器串流恢復
    _accelSub?.cancel();
    _accelSub = accelerometerEventStream().listen((e) {
      _ax = e.x; _ay = e.y; _az = e.z;
      _checkImpact();
    });
  }

  // ── 停止所有 ───────────────────────────────────────────────────────────────
  void stop() {
    _sendTimer?.cancel();
    _accelSub?.cancel();
    _gyroSub?.cancel();
    _sendTimer = null;
    _accelSub  = null;
    _gyroSub   = null;
    _onImpact  = null;
  }

  void stopImpactDetection() {
    _onImpact = null;
    // 若資料上行也沒在跑，才關 accel 訂閱
    if (_sendTimer == null) {
      _accelSub?.cancel();
      _accelSub = null;
    }

  }

  // ── 撞擊偵測邏輯 ──────────────────────────────────────────────────────────
  void _checkImpact() {
    if (_onImpact == null) return;

    // 計算加速度合力（向量大小）
    final magnitude = sqrt(_ax * _ax + _ay * _ay + _az * _az);
    if (magnitude < _impactThreshold) return;

    // 冷卻期內不重複觸發
    final now = DateTime.now();
    if (_lastImpact != null && now.difference(_lastImpact!) < _cooldown) {
      return;
    }

    _lastImpact = now;
    _onImpact!(magnitude);
  }
}
