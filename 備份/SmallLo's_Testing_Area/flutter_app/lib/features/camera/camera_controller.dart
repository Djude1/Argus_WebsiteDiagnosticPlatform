import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/services/camera_stream_service.dart';
import '../../data/services/websocket_service.dart';

/// Notifier for camera state management.
class CameraNotifier extends StateNotifier<AsyncValue<bool>> {
  final Ref _ref;
  final CameraStreamService _cameraService;
  final WebSocketService _wsService;

  CameraNotifier(this._ref, this._cameraService, this._wsService)
      : super(const AsyncValue.loading());

  Future<void> initialize() async {
    state = const AsyncValue.loading();
    try {
      await _cameraService.initialize();
      state = const AsyncValue.data(true);
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }

  Future<void> startStreaming() async {
    try {
      await _cameraService.startStreaming();
      _ref.read(isStreamingProvider.notifier).state = true;
    } catch (e) {
      // Handle error
    }
  }

  Future<void> stopStreaming() async {
    try {
      await _cameraService.stopStreaming();
      _ref.read(isStreamingProvider.notifier).state = false;
    } catch (e) {
      // Handle error
    }
  }

  Future<void> toggleStreaming() async {
    if (_cameraService.isStreaming) {
      await stopStreaming();
    } else {
      await startStreaming();
    }
  }
}

/// Provider for camera notifier.
final cameraNotifierProvider =
    StateNotifierProvider<CameraNotifier, AsyncValue<bool>>((ref) {
  final cameraService = ref.watch(cameraStreamServiceProvider);
  final wsService = ref.watch(webSocketServiceProvider);
  return CameraNotifier(ref, cameraService, wsService);
});
