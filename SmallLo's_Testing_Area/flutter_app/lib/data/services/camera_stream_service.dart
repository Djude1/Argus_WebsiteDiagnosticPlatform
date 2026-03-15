import 'dart:async';
import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image/image.dart' as img;
import 'package:logger/logger.dart';

import '../../core/constants.dart';
import 'websocket_service.dart';

/// Camera stream service for capturing and sending frames to the server.
class CameraStreamService {
  final Logger _logger = Logger();
  final WebSocketService _wsService;

  CameraController? _cameraController;
  bool _isStreaming = false;
  int _fps = AppConstants.cameraFps;
  DateTime? _lastFrameTime;

  final StreamController<int> _fpsController = StreamController<int>.broadcast();
  final StreamController<int> _latencyController = StreamController<int>.broadcast();

  Stream<int> get fpsStream => _fpsController.stream;
  Stream<int> get latencyStream => _latencyController.stream;
  bool get isStreaming => _isStreaming;
  bool get isInitialized => _cameraController?.value.isInitialized ?? false;
  CameraController? get controller => _cameraController;

  CameraStreamService(this._wsService);

  /// Initialize camera.
  Future<void> initialize() async {
    final cameras = await availableCameras();
    if (cameras.isEmpty) {
      _logger.e('No cameras available');
      return;
    }

    // Use back camera by default
    final backCamera = cameras.firstWhere(
      (cam) => cam.lensDirection == CameraLensDirection.back,
      orElse: () => cameras.first,
    );

    _cameraController = CameraController(
      backCamera,
      ResolutionPreset.medium,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.jpeg,
    );

    await _cameraController!.initialize();
    _logger.i('Camera initialized');
  }

  /// Start streaming frames to server.
  Future<void> startStreaming() async {
    if (_cameraController == null || !_cameraController!.value.isInitialized) {
      _logger.e('Camera not initialized');
      return;
    }

    if (_isStreaming) return;

    _isStreaming = true;
    await _wsService.connectCamera();

    _cameraController!.startImageStream(_processFrame);
    _logger.i('Started streaming at $_fps FPS');
  }

  void _processFrame(CameraImage image) {
    if (!_isStreaming) return;

    // FPS throttling: skip frame if not enough time has elapsed
    final now = DateTime.now();
    final frameInterval = Duration(milliseconds: 1000 ~/ _fps);

    if (_lastFrameTime != null) {
      final elapsed = now.difference(_lastFrameTime!);
      if (elapsed < frameInterval) {
        return; // Skip this frame to maintain target FPS
      }
    }

    _lastFrameTime = now;
    final startTime = DateTime.now();

    // Convert to JPEG
    final jpegData = _convertToJpeg(image);

    // Send to server
    _wsService.sendCameraFrame(jpegData);

    // Calculate latency
    final latency = DateTime.now().difference(startTime).inMilliseconds;
    _latencyController.add(latency);
  }

  Uint8List _convertToJpeg(CameraImage image) {
    // Handle JPEG format directly
    if (image.format.group == ImageFormatGroup.jpeg) {
      return image.planes.first.bytes;
    }

    // Validate plane count for YUV formats
    if (image.planes.length < 3) {
      _logger.e('Invalid plane count: ${image.planes.length}, expected 3 for YUV');
      // Return a placeholder black frame instead of crashing
      final placeholder = img.Image(width: image.width, height: image.height);
      return Uint8List.fromList(img.encodeJpg(placeholder, quality: 50));
    }

    // Convert YUV420 to RGB then to JPEG
    final rgbImage = img.Image(width: image.width, height: image.height);

    final yPlane = image.planes[0];
    final uPlane = image.planes[1];
    final vPlane = image.planes[2];

    final yRowStride = yPlane.bytesPerRow;
    final uvRowStride = uPlane.bytesPerRow;
    final uvPixelStride = uPlane.bytesPerRow ~/ (image.width ~/ 2);

    for (int y = 0; y < image.height; y++) {
      for (int x = 0; x < image.width; x++) {
        final yIndex = y * yRowStride + x;
        final uvIndex = (y ~/ 2) * uvRowStride + (x ~/ 2) * uvPixelStride;

        // Bounds checking to prevent crashes on various devices
        if (yIndex >= yPlane.bytes.length ||
            uvIndex >= uPlane.bytes.length ||
            uvIndex >= vPlane.bytes.length) {
          rgbImage.setPixelRgb(x, y, 0, 0, 0);
          continue;
        }

        final yValue = yPlane.bytes[yIndex];
        final uValue = uPlane.bytes[uvIndex];
        final vValue = vPlane.bytes[uvIndex];

        final r = (yValue + 1.402 * (vValue - 128)).clamp(0, 255).toInt();
        final g = (yValue - 0.344 * (uValue - 128) - 0.714 * (vValue - 128))
            .clamp(0, 255)
            .toInt();
        final b = (yValue + 1.772 * (uValue - 128)).clamp(0, 255).toInt();

        rgbImage.setPixelRgb(x, y, r, g, b);
      }
    }

    return Uint8List.fromList(
      img.encodeJpg(rgbImage, quality: AppConstants.jpegQuality),
    );
  }

  /// Stop streaming.
  Future<void> stopStreaming() async {
    if (!_isStreaming) return;

    _isStreaming = false;

    if (_cameraController?.value.isStreamingImages ?? false) {
      await _cameraController!.stopImageStream();
    }

    _logger.i('Stopped streaming');
  }

  /// Set FPS.
  void setFps(int fps) {
    _fps = fps.clamp(1, 30);
    _fpsController.add(_fps);
  }

  /// Dispose resources.
  Future<void> dispose() async {
    await stopStreaming();
    await _cameraController?.dispose();
    _fpsController.close();
    _latencyController.close();
  }
}

/// Provider for camera stream service.
final cameraStreamServiceProvider = Provider<CameraStreamService>((ref) {
  final wsService = ref.watch(webSocketServiceProvider);
  final service = CameraStreamService(wsService);
  ref.onDispose(() => service.dispose());
  return service;
});

/// Provider for camera FPS.
final cameraFpsProvider = StreamProvider<int>((ref) {
  final service = ref.watch(cameraStreamServiceProvider);
  return service.fpsStream;
});

/// Provider for camera latency.
final cameraLatencyProvider = StreamProvider<int>((ref) {
  final service = ref.watch(cameraStreamServiceProvider);
  return service.latencyStream;
});

/// Provider for camera streaming state.
final isStreamingProvider = StateProvider<bool>((ref) => false);

/// Provider for available cameras.
final availableCamerasProvider = FutureProvider<List<CameraDescription>>((ref) {
  return availableCameras();
});
