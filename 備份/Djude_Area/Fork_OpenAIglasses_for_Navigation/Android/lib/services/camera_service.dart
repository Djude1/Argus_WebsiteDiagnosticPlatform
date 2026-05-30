// lib/services/camera_service.dart
// 攝影機管理：取得 JPEG 幀並送到 WebSocket
//
// 策略：用 takePicture 走相機硬體 JPEG encoder（CPU 不重，debug/release 都能跑）
//      + 動態 fps：待機（IDLE/CHAT）2 fps、導航中 10 fps，由 AppProvider 監聽
//      NAV_STATE: 切換呼叫 setFps()，待機時降 capture pipeline 觸發頻率 5 倍。

import 'dart:async';
import 'dart:typed_data';
import 'package:camera/camera.dart';

typedef FrameCallback = void Function(Uint8List jpegBytes);

class CameraService {
  CameraController? _controller;
  Timer?            _timer;
  bool              _running = false;
  FrameCallback?    _onFrame;
  int               _currentFps = 10;

  /// 初始化攝影機（預設使用後鏡頭）
  Future<void> initialize() async {
    final cameras = await availableCameras();
    if (cameras.isEmpty) throw Exception('找不到攝影機');

    // 優先選後鏡頭
    final cam = cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => cameras.first,
    );

    _controller = CameraController(
      cam,
      ResolutionPreset.medium, // 中等畫質，降低頻寬
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.jpeg,
    );
    await _controller!.initialize();
    // 明確關閉閃光燈，避免部分裝置在連續拍照時自動開啟輔助燈
    await _controller!.setFlashMode(FlashMode.off);
  }

  /// 開始以 fps 速率送幀
  void startStreaming({required FrameCallback onFrame, int fps = 10}) {
    if (_running) return;
    _running = true;
    _onFrame = onFrame;
    _currentFps = fps;
    _startTimer();
  }

  /// 動態調整 fps（待機 ↔ 導航時切換）。fps 相同則 no-op。
  void setFps(int fps) {
    if (fps <= 0 || fps == _currentFps) return;
    _currentFps = fps;
    if (_running) _startTimer();
  }

  int get currentFps => _currentFps;

  void _startTimer() {
    _timer?.cancel();
    if (!_running) return;
    final interval = Duration(milliseconds: (1000 / _currentFps).round());
    _timer = Timer.periodic(interval, (_) async {
      final ctrl = _controller;
      if (ctrl == null || !ctrl.value.isInitialized) return;
      try {
        final xfile = await ctrl.takePicture();
        final bytes = await xfile.readAsBytes();
        _onFrame?.call(bytes);
      } catch (_) {
        // 拍照失敗時不停止 timer，維持週期嘗試
      }
    });
  }

  void stopStreaming() {
    _running = false;
    _onFrame = null;
    _timer?.cancel();
    _timer = null;
  }

  Future<void> dispose() async {
    stopStreaming();
    await _controller?.dispose();
    _controller = null;
  }

  CameraController? get controller => _controller;
  bool get isInitialized => _controller?.value.isInitialized ?? false;
}
