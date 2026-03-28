// lib/services/camera_service.dart
// 攝影機管理：取得 JPEG 幀並送到 WebSocket

import 'dart:async';
import 'dart:typed_data';
import 'package:camera/camera.dart';

typedef FrameCallback = void Function(Uint8List jpegBytes);

class CameraService {
  CameraController? _controller;
  Timer?            _timer;
  bool              _running = false;

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
    final interval = Duration(milliseconds: (1000 / fps).round());
    _timer = Timer.periodic(interval, (_) async {
      if (_controller == null || !_controller!.value.isInitialized) return;
      try {
        final xfile = await _controller!.takePicture();
        final bytes = await xfile.readAsBytes();
        onFrame(bytes);
      } catch (_) {
        // 拍照失敗時重置旗標，讓下一幀可以重試
        // 不停止 timer，維持週期嘗試
      }
    });
  }

  void stopStreaming() {
    _running = false;
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
