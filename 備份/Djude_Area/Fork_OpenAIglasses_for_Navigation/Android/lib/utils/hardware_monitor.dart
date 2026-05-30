// 讀取手機硬體效能（CPU % / APP 記憶體 / 溫度）
// CPU：經由 Platform Channel 讓 Kotlin 讀 /proc/self/stat（APP 自身，SELinux 允許）
// RAM：dart:io ProcessInfo.currentRss（APP 自身 RSS，無需系統權限）
// 溫度：/sys/class/thermal/...（封鎖時顯示 -1，停止重試）
// 僅用於 AR 測試頁 + debug 畫面，一般使用者畫面不顯示

import 'dart:async';
import 'dart:io';
import 'package:flutter/services.dart';

class HardwareMonitor {
  int cpuPercent = 0;   // APP 自身 CPU 使用率 %
  int appRamMB   = 0;   // APP 自身記憶體用量 MB
  int tempC      = 0;   // 手機溫度（不可讀時為 -1）

  bool _tempBlocked = false;

  static const _ch = MethodChannel('com.aiglasses/app_control');

  Timer? _timer;

  void start(void Function() onUpdate) {
    _timer = Timer.periodic(const Duration(seconds: 1), (_) async {
      cpuPercent = await _readCpuPercent();
      appRamMB   = _readRamMB();
      if (!_tempBlocked) tempC = await _readTempC();
      onUpdate();
    });
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  // Kotlin 讀 /proc/self/stat → 回傳 int
  Future<int> _readCpuPercent() async {
    try {
      final pct = await _ch.invokeMethod<int>('getCpuPercent');
      return pct ?? cpuPercent;
    } catch (_) {
      return cpuPercent;
    }
  }

  // dart:io ProcessInfo.currentRss：APP 自身 RSS，無需系統權限
  int _readRamMB() {
    try {
      return ProcessInfo.currentRss ~/ (1024 * 1024);
    } catch (_) {
      return appRamMB;
    }
  }

  static const _tempPaths = [
    '/sys/class/thermal/thermal_zone0/temp',
    '/sys/class/thermal/thermal_zone1/temp',
    '/sys/devices/virtual/thermal/thermal_zone0/temp',
  ];

  Future<int> _readTempC() async {
    for (final path in _tempPaths) {
      try {
        final raw = (await File(path).readAsString()).trim();
        final val = int.parse(raw);
        return val > 1000 ? val ~/ 1000 : val;
      } catch (_) {}
    }
    _tempBlocked = true;
    return -1;
  }
}
