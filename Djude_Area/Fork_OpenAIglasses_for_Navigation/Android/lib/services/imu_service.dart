// lib/services/imu_service.dart
// 手機 IMU（加速度計 + 陀螺儀）→ WebSocket /ws JSON 上行
// 格式：{"accel":{"x":...,"y":...,"z":...},"gyro":{"x":...,"y":...,"z":...}}

import 'dart:async';
import 'package:sensors_plus/sensors_plus.dart';

typedef ImuCallback = void Function(Map<String, dynamic> data);

class ImuService {
  StreamSubscription? _accelSub;
  StreamSubscription? _gyroSub;

  double _ax = 0, _ay = 0, _az = 0;
  double _gx = 0, _gy = 0, _gz = 0;
  Timer? _sendTimer;

  /// 開始收集 IMU 並以 intervalMs 毫秒為間隔回呼
  void start({required ImuCallback onData, int intervalMs = 100}) {
    _accelSub = accelerometerEventStream().listen((e) {
      _ax = e.x; _ay = e.y; _az = e.z;
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

  void stop() {
    _sendTimer?.cancel();
    _accelSub?.cancel();
    _gyroSub?.cancel();
    _sendTimer = null;
    _accelSub  = null;
    _gyroSub   = null;
  }
}
