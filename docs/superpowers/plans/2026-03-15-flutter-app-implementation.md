# Flutter App Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Flutter Android app that connects to the existing FastAPI server for camera streaming and voice chat functionality, replacing ESP32 hardware with mobile sensors.

**Architecture:** WebSocket-based communication with FastAPI server. Riverpod for state management. Camera stream sends frames to server, receives annotated images. Voice chat sends PCM16 audio, receives AI responses.

**Tech Stack:** Flutter 3.x, Riverpod, camera, web_socket_channel, record, audioplayers, shared_preferences

---

## File Structure Overview

```
flutter_app/
├── lib/
│   ├── main.dart                          # App entry point
│   ├── app.dart                           # MaterialApp + Riverpod
│   ├── core/
│   │   ├── constants.dart                 # API endpoints, defaults
│   │   └── theme.dart                     # Dark theme matching web UI
│   ├── data/
│   │   ├── services/
│   │   │   ├── websocket_service.dart     # WebSocket connection manager
│   │   │   ├── camera_stream_service.dart # Camera → server → display
│   │   │   └── audio_service.dart         # Recording + playback
│   │   └── models/
│   │       └── server_config.dart         # Server connection config (freezed)
│   ├── features/
│   │   ├── camera/
│   │   │   ├── camera_viewer.dart         # Live image display widget
│   │   │   └── camera_controller.dart     # Camera state provider
│   │   ├── voice/
│   │   │   ├── voice_input.dart           # Push-to-talk button
│   │   │   ├── voice_output.dart          # AI response playback
│   │   │   └── chat_panel.dart            # Chat history display
│   │   └── settings/
│   │       └── server_settings.dart       # Server IP/Port settings
│   ├── shared/
│   │   ├── widgets/
│   │   │   ├── status_indicator.dart      # Connection status badge
│   │   │   └── loading_overlay.dart       # Loading overlay
│   │   └── providers/
│   │       └── app_state.dart             # Global state providers
│   └── pages/
│       ├── main_page.dart                 # Home page with camera + voice
│       ├── settings_page.dart             # Server settings
│       └── history_page.dart              # Chat history (placeholder)
├── pubspec.yaml                           # Dependencies
├── android/
│   └── app/src/main/AndroidManifest.xml   # Permissions
└── test/
    └── widget_test.dart                   # Basic widget tests
```

---

## Chunk 1: Project Setup

### Task 1.1: Create Flutter Project

**Files:**
- Create: `flutter_app/` (via flutter create)

- [ ] **Step 1: Create Flutter project**

```bash
cd C:\Users\owo\Desktop\OpenAIDevice_For_VisualImpairment
flutter create --platforms android flutter_app
```

Expected: Flutter project created successfully

- [ ] **Step 2: Verify project structure**

```bash
ls flutter_app/
```

Expected: `android/`, `lib/`, `pubspec.yaml`, `test/` directories exist

- [ ] **Step 3: Commit**

```bash
cd flutter_app
git add .
git commit -m "feat: initialize Flutter project"
```

---

### Task 1.2: Configure Dependencies

**Files:**
- Modify: `flutter_app/pubspec.yaml`

- [ ] **Step 1: Update pubspec.yaml with dependencies**

Replace `pubspec.yaml` dependencies section:

```yaml
name: visual_impairment_assistant
description: A Flutter app for visual impairment assistance using AI.
publish_to: 'none'
version: 1.0.0+1

environment:
  sdk: '>=3.0.0 <4.0.0'

dependencies:
  flutter:
    sdk: flutter

  # State management
  flutter_riverpod: ^2.4.9

  # Network
  web_socket_channel: ^2.4.0

  # Camera
  camera: ^0.10.5+7
  image: ^4.1.3

  # Audio
  record: ^5.0.4
  audioplayers: ^5.2.1

  # Permissions
  permission_handler: ^11.1.0

  # Utilities
  connectivity_plus: ^5.0.2
  shared_preferences: ^2.2.2
  uuid: ^4.2.2
  logger: ^2.0.2+1
  freezed_annotation: ^2.4.0

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^3.0.1
  build_runner: ^2.4.7
  freezed: ^2.4.6

flutter:
  uses-material-design: true
```

- [ ] **Step 2: Get dependencies**

```bash
cd flutter_app
flutter pub get
```

Expected: Dependencies resolved successfully

- [ ] **Step 3: Commit**

```bash
git add pubspec.yaml pubspec.lock
git commit -m "feat: add project dependencies"
```

---

### Task 1.3: Configure Android Permissions

**Files:**
- Modify: `flutter_app/android/app/src/main/AndroidManifest.xml`

- [ ] **Step 1: Add permissions to AndroidManifest.xml**

Replace the entire AndroidManifest.xml:

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <!-- Network permissions -->
    <uses-permission android:name="android.permission.INTERNET"/>
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE"/>
    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE"/>

    <!-- Camera permissions -->
    <uses-permission android:name="android.permission.CAMERA"/>
    <uses-feature android:name="android.hardware.camera" android:required="true"/>
    <uses-feature android:name="android.hardware.camera.autofocus" android:required="false"/>

    <!-- Microphone permissions -->
    <uses-permission android:name="android.permission.RECORD_AUDIO"/>
    <uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS"/>

    <!-- Bluetooth (for audio output) -->
    <uses-permission android:name="android.permission.BLUETOOTH"/>
    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT"/>

    <application
        android:label="視障輔助"
        android:name="${applicationName}"
        android:icon="@mipmap/ic_launcher"
        android:usesCleartextTraffic="true">
        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:launchMode="singleTop"
            android:theme="@style/LaunchTheme"
            android:configChanges="orientation|keyboardHidden|keyboard|screenSize|smallestScreenSize|locale|layoutDirection|fontScale|screenLayout|density|uiMode"
            android:hardwareAccelerated="true"
            android:windowSoftInputMode="adjustResize">
            <meta-data
              android:name="io.flutter.embedding.android.NormalTheme"
              android:resource="@style/NormalTheme"
              />
            <intent-filter>
                <action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/>
            </intent-filter>
        </activity>
        <meta-data
            android:name="flutterEmbedding"
            android:value="2" />
    </application>
</manifest>
```

- [ ] **Step 2: Commit**

```bash
git add android/app/src/main/AndroidManifest.xml
git commit -m "feat: add Android permissions for camera, mic, and network"
```

---

## Chunk 2: Core Infrastructure

### Task 2.1: Constants and Theme

**Files:**
- Create: `flutter_app/lib/core/constants.dart`
- Create: `flutter_app/lib/core/theme.dart`

- [ ] **Step 1: Create constants.dart**

```dart
// lib/core/constants.dart
/// App-wide constants
class AppConstants {
  AppConstants._();

  /// Default server configuration
  static const String defaultServerIp = '192.168.1.100';
  static const int defaultServerPort = 8081;

  /// WebSocket endpoints
  static String wsCameraEndpoint(String ip, int port) =>
      'ws://$ip:$port/ws/camera';
  static String wsViewerEndpoint(String ip, int port) =>
      'ws://$ip:$port/ws/viewer';
  static String wsAudioEndpoint(String ip, int port) =>
      'ws://$ip:$port/ws_audio';

  /// Audio settings
  static const int audioSampleRate = 16000;
  static const int audioChunkMs = 20;

  /// Connection settings
  static const Duration connectionTimeout = Duration(seconds: 10);
  static const Duration reconnectDelay = Duration(seconds: 2);
  static const int maxReconnectAttempts = 3;
}

/// SharedPreferences keys
class PreferenceKeys {
  PreferenceKeys._();

  static const String serverIp = 'server_ip';
  static const String serverPort = 'server_port';
}
```

- [ ] **Step 2: Create theme.dart**

```dart
// lib/core/theme.dart
import 'package:flutter/material.dart';

/// Dark theme matching the web UI style
class AppTheme {
  AppTheme._();

  static const Color background = Color(0xFF0B0F14);
  static const Color card = Color(0xFF121821);
  static const Color text = Color(0xFFE6EDF3);
  static const Color muted = Color(0xFF9FB0C3);
  static const Color success = Color(0xFF7EE787);
  static const Color error = Color(0xFFFF8080);
  static const Color line = Color(0xFF1F2937);
  static const Color accent = Color(0xFF2F86FF);

  static ThemeData get dark {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: background,
      colorScheme: const ColorScheme.dark(
        primary: accent,
        secondary: accent,
        surface: card,
        error: error,
        onSurface: text,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: card,
        foregroundColor: text,
        elevation: 0,
      ),
      cardTheme: CardTheme(
        color: card,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: const BorderSide(color: line),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: accent,
          foregroundColor: text,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: card,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: line),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: line),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: accent),
        ),
        labelStyle: const TextStyle(color: muted),
      ),
      textTheme: const TextTheme(
        bodyLarge: TextStyle(color: text),
        bodyMedium: TextStyle(color: text),
        titleLarge: TextStyle(color: text, fontWeight: FontWeight.bold),
      ),
    );
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add lib/core/
git commit -m "feat: add constants and dark theme"
```

---

### Task 2.2: Server Config Model (Freezed)

**Files:**
- Create: `flutter_app/lib/data/models/server_config.dart`
- Create: `flutter_app/lib/data/models/server_config.freezed.dart` (generated)

- [ ] **Step 1: Create server_config.dart with freezed**

```dart
// lib/data/models/server_config.dart
import 'package:freezed_annotation/freezed_annotation.dart';

part 'server_config.freezed.dart';

@freezed
class ServerConfig with _$ServerConfig {
  const factory ServerConfig({
    required String ip,
    required int port,
  }) = _ServerConfig;

  factory ServerConfig.defaults() => const ServerConfig(
        ip: '192.168.1.100',
        port: 8081,
      );
}
```

- [ ] **Step 2: Run build_runner to generate code**

```bash
cd flutter_app
dart run build_runner build --delete-conflicting-outputs
```

Expected: `server_config.freezed.dart` generated

- [ ] **Step 3: Commit**

```bash
git add lib/data/models/
git commit -m "feat: add ServerConfig model with freezed"
```

---

### Task 2.3: WebSocket Service

**Files:**
- Create: `flutter_app/lib/data/services/websocket_service.dart`

- [ ] **Step 1: Create WebSocketService**

```dart
// lib/data/services/websocket_service.dart
import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:logger/logger.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../../core/constants.dart';
import '../models/server_config.dart';

/// Connection state enum
enum ConnectionState {
  disconnected,
  connecting,
  connected,
  reconnecting,
  error,
}

/// WebSocket service managing multiple connections
class WebSocketService {
  final Logger _logger = Logger();
  final ServerConfig _config;

  WebSocketChannel? _cameraChannel;
  WebSocketChannel? _viewerChannel;
  WebSocketChannel? _audioChannel;

  final StreamController<Uint8List> _viewerFrameController =
      StreamController<Uint8List>.broadcast();
  final StreamController<Uint8List> _audioResponseController =
      StreamController<Uint8List>.broadcast();
  final StreamController<ConnectionState> _connectionStateController =
      StreamController<ConnectionState>.broadcast();

  Stream<Uint8List> get viewerFrames => _viewerFrameController.stream;
  Stream<Uint8List> get audioResponses => _audioResponseController.stream;
  Stream<ConnectionState> get connectionState => _connectionStateController.stream;

  ConnectionState _currentState = ConnectionState.disconnected;
  ConnectionState get currentState => _currentState;

  WebSocketService(this._config);

  /// Connect all WebSocket channels
  Future<void> connect() async {
    if (_currentState == ConnectionState.connected ||
        _currentState == ConnectionState.connecting) {
      return;
    }

    _updateState(ConnectionState.connecting);
    _logger.i('Connecting to server at ${_config.ip}:${_config.port}');

    try {
      // Connect viewer channel (receives annotated frames)
      final viewerUri = Uri.parse(
        AppConstants.wsViewerEndpoint(_config.ip, _config.port),
      );
      _viewerChannel = WebSocketChannel.connect(viewerUri);
      _viewerChannel!.stream.listen(
        (data) {
          if (data is List<int>) {
            _viewerFrameController.add(Uint8List.fromList(data));
          }
        },
        onError: (error) => _handleError('Viewer', error),
        onDone: () => _handleDisconnect('Viewer'),
      );

      // Connect audio channel (bidirectional)
      final audioUri = Uri.parse(
        AppConstants.wsAudioEndpoint(_config.ip, _config.port),
      );
      _audioChannel = WebSocketChannel.connect(audioUri);
      _audioChannel!.stream.listen(
        (data) {
          if (data is List<int>) {
            _audioResponseController.add(Uint8List.fromList(data));
          }
        },
        onError: (error) => _handleError('Audio', error),
        onDone: () => _handleDisconnect('Audio'),
      );

      // Connect camera channel (sends frames)
      final cameraUri = Uri.parse(
        AppConstants.wsCameraEndpoint(_config.ip, _config.port),
      );
      _cameraChannel = WebSocketChannel.connect(cameraUri);

      _updateState(ConnectionState.connected);
      _logger.i('Connected to server successfully');
    } catch (e) {
      _logger.e('Failed to connect: $e');
      _updateState(ConnectionState.error);
      rethrow;
    }
  }

  /// Send camera frame to server
  void sendCameraFrame(Uint8List jpegBytes) {
    _cameraChannel?.sink.add(jpegBytes);
  }

  /// Send audio data to server
  void sendAudioData(Uint8List pcmData) {
    _audioChannel?.sink.add(pcmData);
  }

  /// Disconnect all channels
  Future<void> disconnect() async {
    _logger.i('Disconnecting from server');
    await _cameraChannel?.sink.close();
    await _viewerChannel?.sink.close();
    await _audioChannel?.sink.close();
    _cameraChannel = null;
    _viewerChannel = null;
    _audioChannel = null;
    _updateState(ConnectionState.disconnected);
  }

  void _updateState(ConnectionState state) {
    _currentState = state;
    _connectionStateController.add(state);
  }

  void _handleError(String channel, dynamic error) {
    _logger.e('$channel channel error: $error');
    _updateState(ConnectionState.error);
  }

  void _handleDisconnect(String channel) {
    _logger.w('$channel channel disconnected');
    if (_currentState == ConnectionState.connected) {
      _updateState(ConnectionState.disconnected);
    }
  }

  void dispose() {
    disconnect();
    _viewerFrameController.close();
    _audioResponseController.close();
    _connectionStateController.close();
  }
}

/// Provider for WebSocketService
final websocketServiceProvider = StateNotifierProvider<
    WebSocketNotifier, AsyncValue<WebSocketService>>((ref) {
  final config = ref.watch(serverConfigProvider);
  return WebSocketNotifier(config);
});

class WebSocketNotifier extends StateNotifier<AsyncValue<WebSocketService>> {
  WebSocketNotifier(ServerConfig config)
      : super(AsyncValue.data(WebSocketService(config)));

  Future<void> connect() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() async {
      final service = state.value!;
      await service.connect();
      return service;
    });
  }

  Future<void> disconnect() async {
    await state.value?.disconnect();
  }
}

/// Provider for server configuration
final serverConfigProvider = StateProvider<ServerConfig>((ref) {
  return ServerConfig.defaults();
});
```

- [ ] **Step 2: Commit**

```bash
git add lib/data/services/websocket_service.dart
git commit -m "feat: add WebSocket service with connection management"
```

---

## Chunk 3: Camera Feature

### Task 3.1: Camera Stream Service

**Files:**
- Create: `flutter_app/lib/data/services/camera_stream_service.dart`

- [ ] **Step 1: Create CameraStreamService**

```dart
// lib/data/services/camera_stream_service.dart
import 'dart:async';
import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image/image.dart' as img;
import 'package:logger/logger.dart';

import 'websocket_service.dart';

/// Camera stream service handling capture and send
class CameraStreamService {
  final Logger _logger = Logger();
  final WebSocketService _wsService;

  CameraController? _controller;
  bool _isStreaming = false;
  int _frameCount = 0;
  DateTime? _lastFpsUpdate;
  double _currentFps = 0;

  final StreamController<double> _fpsController =
      StreamController<double>.broadcast();

  Stream<double> get fpsStream => _fpsController.stream;
  double get currentFps => _currentFps;
  bool get isStreaming => _isStreaming;
  bool get isInitialized => _controller?.value.isInitialized ?? false;

  CameraStreamService(this._wsService);

  /// Initialize camera
  Future<void> initialize() async {
    final cameras = await availableCameras();
    if (cameras.isEmpty) {
      throw Exception('No cameras available');
    }

    // Use back camera
    final backCamera = cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => cameras.first,
    );

    _controller = CameraController(
      backCamera,
      ResolutionPreset.medium,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.jpeg,
    );

    await _controller!.initialize();
    _logger.i('Camera initialized: ${backCamera.name}');
  }

  /// Start streaming frames to server
  Future<void> startStreaming() async {
    if (_controller == null || !_controller!.value.isInitialized) {
      await initialize();
    }

    if (_isStreaming) return;

    _isStreaming = true;
    _frameCount = 0;
    _lastFpsUpdate = DateTime.now();

    _controller!.startImageStream(_onFrame);
    _logger.i('Camera streaming started');
  }

  /// Stop streaming
  Future<void> stopStreaming() async {
    if (!_isStreaming) return;

    await _controller?.stopImageStream();
    _isStreaming = false;
    _logger.i('Camera streaming stopped');
  }

  void _onFrame(CameraImage image) {
    if (!_isStreaming) return;

    // Convert to JPEG
    final jpegBytes = _convertToJpeg(image);
    if (jpegBytes != null) {
      _wsService.sendCameraFrame(jpegBytes);
      _updateFps();
    }
  }

  Uint8List? _convertToJpeg(CameraImage image) {
    try {
      // Handle different formats
      img.Image? convertedImage;

      if (image.format.group == ImageFormatGroup.jpeg) {
        // Already JPEG, return as-is
        return image.planes.first.bytes;
      } else if (image.format.group == ImageFormatGroup.yuv420) {
        // Convert YUV420 to RGB
        convertedImage = _yuv420ToImage(image);
      } else if (image.format.group == ImageFormatGroup.bgra8888) {
        // Convert BGRA to RGB
        convertedImage = _bgra8888ToImage(image);
      }

      if (convertedImage == null) return null;

      // Encode to JPEG
      return Uint8List.fromList(img.encodeJpg(convertedImage, quality: 70));
    } catch (e) {
      _logger.e('Failed to convert frame: $e');
      return null;
    }
  }

  img.Image _yuv420ToImage(CameraImage image) {
    final int width = image.width;
    final int height = image.height;

    final yPlane = image.planes[0];
    final uPlane = image.planes[1];
    final vPlane = image.planes[2];

    final yBuffer = yPlane.bytes;
    final uBuffer = uPlane.bytes;
    final vBuffer = vPlane.bytes;

    final int yRowStride = yPlane.bytesPerRow;
    final int uvRowStride = uPlane.bytesPerRow;
    final int uvPixelStride = uPlane.bytesPerPixel ?? 1;

    final rgbImage = img.Image(width: width, height: height);

    for (int y = 0; y < height; y++) {
      for (int x = 0; x < width; x++) {
        final int yIndex = y * yRowStride + x;
        final int uvIndex = (y ~/ 2) * uvRowStride + (x ~/ 2) * uvPixelStride;

        final int yValue = yBuffer[yIndex];
        final int uValue = uBuffer[uvIndex];
        final int vValue = vBuffer[uvIndex];

        // YUV to RGB conversion
        int r = (yValue + 1.402 * (vValue - 128)).round().clamp(0, 255);
        int g = (yValue - 0.344136 * (uValue - 128) - 0.714136 * (vValue - 128))
            .round()
            .clamp(0, 255);
        int b = (yValue + 1.772 * (uValue - 128)).round().clamp(0, 255);

        rgbImage.setPixelRgba(x, y, r, g, b);
      }
    }

    return rgbImage;
  }

  img.Image _bgra8888ToImage(CameraImage image) {
    final int width = image.width;
    final int height = image.height;
    final plane = image.planes.first;
    final bytes = plane.bytes;

    final rgbImage = img.Image(width: width, height: height);

    for (int y = 0; y < height; y++) {
      for (int x = 0; x < width; x++) {
        final int index = (y * width + x) * 4;
        final int b = bytes[index];
        final int g = bytes[index + 1];
        final int r = bytes[index + 2];
        rgbImage.setPixelRgba(x, y, r, g, b);
      }
    }

    return rgbImage;
  }

  void _updateFps() {
    _frameCount++;
    final now = DateTime.now();
    if (_lastFpsUpdate != null) {
      final elapsed = now.difference(_lastFpsUpdate!).inMilliseconds;
      if (elapsed >= 1000) {
        _currentFps = _frameCount * 1000 / elapsed;
        _fpsController.add(_currentFps);
        _frameCount = 0;
        _lastFpsUpdate = now;
      }
    }
  }

  Future<void> dispose() async {
    await stopStreaming();
    await _controller?.dispose();
    _fpsController.close();
  }
}

/// Provider for camera service
final cameraStreamServiceProvider = StateNotifierProvider<
    CameraStreamNotifier, AsyncValue<CameraStreamService>>((ref) {
  final wsService = ref.watch(websocketServiceProvider).value;
  if (wsService == null) {
    return CameraStreamNotifier(null);
  }
  return CameraStreamNotifier(CameraStreamService(wsService));
});

class CameraStreamNotifier extends StateNotifier<AsyncValue<CameraStreamService>> {
  CameraStreamNotifier(CameraStreamService? service)
      : super(service != null
            ? AsyncValue.data(service)
            : const AsyncValue.loading());

  Future<void> initialize() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() async {
      final service = CameraStreamService(
          // Will be set from provider
          StateNotifierProvider<WebSocketNotifier, AsyncValue<WebSocketService>>(
                  (ref) => WebSocketNotifier(ServerConfig.defaults()))
              .toString() as WebSocketService);
      await service.initialize();
      return service;
    });
  }

  Future<void> startStreaming() async {
    await state.value?.startStreaming();
  }

  Future<void> stopStreaming() async {
    await state.value?.stopStreaming();
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add lib/data/services/camera_stream_service.dart
git commit -m "feat: add camera stream service with YUV/JPEG conversion"
```

---

### Task 3.2: Camera Viewer Widget

**Files:**
- Create: `flutter_app/lib/features/camera/camera_viewer.dart`

- [ ] **Step 1: Create CameraViewer widget**

```dart
// lib/features/camera/camera_viewer.dart
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme.dart';
import '../../data/services/websocket_service.dart';

/// Camera viewer displaying annotated frames from server
class CameraViewer extends ConsumerWidget {
  const CameraViewer({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final connectionState = ref.watch(
      websocketServiceProvider.select((s) => s.value?.currentState),
    );
    final frameStream = ref.watch(
      websocketServiceProvider.select((s) => s.value?.viewerFrames),
    );

    if (connectionState != ConnectionState.connected) {
      return _buildDisconnectedState(context);
    }

    return StreamBuilder<Uint8List>(
      stream: frameStream,
      builder: (context, snapshot) {
        if (snapshot.hasData) {
          return _buildFrameDisplay(snapshot.data!);
        }

        if (snapshot.hasError) {
          return _buildErrorState(context, snapshot.error.toString());
        }

        return _buildWaitingState(context);
      },
    );
  }

  Widget _buildFrameDisplay(Uint8List jpegBytes) {
    return Container(
      color: Colors.black,
      child: Center(
        child: Image.memory(
          jpegBytes,
          fit: BoxFit.contain,
          gaplessPlayback: true, // Smooth frame transitions
        ),
      ),
    );
  }

  Widget _buildDisconnectedState(BuildContext context) {
    return Container(
      color: AppTheme.background,
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.videocam_off,
              size: 64,
              color: AppTheme.muted,
            ),
            const SizedBox(height: 16),
            Text(
              '未連接到伺服器',
              style: TextStyle(
                color: AppTheme.muted,
                fontSize: 16,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildWaitingState(BuildContext context) {
    return Container(
      color: AppTheme.background,
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: 16),
            Text(
              '等待影像串流...',
              style: TextStyle(
                color: AppTheme.muted,
                fontSize: 16,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorState(BuildContext context, String error) {
    return Container(
      color: AppTheme.background,
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.error_outline,
              size: 64,
              color: AppTheme.error,
            ),
            const SizedBox(height: 16),
            Text(
              '影像錯誤',
              style: TextStyle(
                color: AppTheme.error,
                fontSize: 16,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              error,
              style: TextStyle(
                color: AppTheme.muted,
                fontSize: 12,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add lib/features/camera/camera_viewer.dart
git commit -m "feat: add camera viewer widget for displaying annotated frames"
```

---

## Chunk 4: Audio Feature

### Task 4.1: Audio Service

**Files:**
- Create: `flutter_app/lib/data/services/audio_service.dart`

- [ ] **Step 1: Create AudioService**

```dart
// lib/data/services/audio_service.dart
import 'dart:async';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:logger/logger.dart';
import 'package:record/record.dart';

import '../../core/constants.dart';
import 'websocket_service.dart';

/// Audio recording state
enum RecordingState {
  idle,
  recording,
  sending,
}

/// Audio service for recording and playback
class AudioService {
  final Logger _logger = Logger();
  final WebSocketService _wsService;

  final AudioRecorder _recorder = AudioRecorder();
  final AudioPlayer _player = AudioPlayer();

  RecordingState _recordingState = RecordingState.idle;
  bool _isPlaying = false;

  final StreamController<RecordingState> _recordingStateController =
      StreamController<RecordingState>.broadcast();
  final StreamController<String> _transcriptController =
      StreamController<String>.broadcast();

  Stream<RecordingState> get recordingState => _recordingStateController.stream;
  Stream<String> get transcript => _transcriptController.stream;
  RecordingState get currentRecordingState => _recordingState;
  bool get isPlaying => _isPlaying;

  AudioService(this._wsService);

  /// Start recording audio
  Future<void> startRecording() async {
    if (_recordingState != RecordingState.idle) return;

    final hasPermission = await _recorder.hasPermission();
    if (!hasPermission) {
      throw Exception('Microphone permission not granted');
    }

    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: AppConstants.audioSampleRate,
        numChannels: 1,
      ),
    );

    _updateRecordingState(RecordingState.recording);
    _logger.i('Audio recording started');
  }

  /// Stop recording and send to server
  Future<void> stopRecording() async {
    if (_recordingState != RecordingState.recording) return;

    _updateRecordingState(RecordingState.sending);

    final audioData = await _recorder.stop();
    if (audioData != null) {
      // Read the recorded file and send to server
      // Note: For real-time streaming, we'd use a different approach
      _logger.i('Audio recording stopped, data: $audioData');
    }

    _updateRecordingState(RecordingState.idle);
  }

  /// Send PCM16 audio chunk to server (for real-time streaming)
  void sendAudioChunk(Uint8List pcmData) {
    if (_recordingState == RecordingState.recording) {
      _wsService.sendAudioData(pcmData);
    }
  }

  /// Play audio from bytes
  Future<void> playAudio(Uint8List audioBytes) async {
    if (_isPlaying) {
      await _player.stop();
    }

    _isPlaying = true;
    await _player.play(BytesSource(audioBytes));
    _player.onPlayerComplete.listen((_) {
      _isPlaying = false;
    });
  }

  /// Stop playback
  Future<void> stopPlayback() async {
    await _player.stop();
    _isPlaying = false;
  }

  void _updateRecordingState(RecordingState state) {
    _recordingState = state;
    _recordingStateController.add(state);
  }

  Future<void> dispose() async {
    await _recorder.stop();
    await _player.dispose();
    _recordingStateController.close();
    _transcriptController.close();
  }
}

/// Provider for audio service
final audioServiceProvider = StateNotifierProvider<AudioNotifier,
    AsyncValue<AudioService>>((ref) {
  final wsService = ref.watch(websocketServiceProvider).value;
  if (wsService == null) {
    return AudioNotifier(null);
  }
  return AudioNotifier(AudioService(wsService));
});

class AudioNotifier extends StateNotifier<AsyncValue<AudioService>> {
  AudioNotifier(AudioService? service)
      : super(service != null
            ? AsyncValue.data(service)
            : const AsyncValue.loading());

  Future<void> startRecording() async {
    await state.value?.startRecording();
  }

  Future<void> stopRecording() async {
    await state.value?.stopRecording();
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add lib/data/services/audio_service.dart
git commit -m "feat: add audio service for recording and playback"
```

---

### Task 4.2: Voice Input Widget

**Files:**
- Create: `flutter_app/lib/features/voice/voice_input.dart`

- [ ] **Step 1: Create VoiceInput widget**

```dart
// lib/features/voice/voice_input.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme.dart';
import '../../data/services/audio_service.dart';

/// Push-to-talk voice input button
class VoiceInput extends ConsumerStatefulWidget {
  const VoiceInput({super.key});

  @override
  ConsumerState<VoiceInput> createState() => _VoiceInputState();
}

class _VoiceInputState extends ConsumerState<VoiceInput> {
  bool _isPressed = false;

  @override
  Widget build(BuildContext context) {
    final recordingState = ref.watch(
      audioServiceProvider.select((s) => s.value?.currentRecordingState),
    );
    final isRecording = recordingState == RecordingState.recording;

    return GestureDetector(
      onTapDown: (_) => _startRecording(),
      onTapUp: (_) => _stopRecording(),
      onTapCancel: () => _stopRecording(),
      child: Container(
        width: 120,
        height: 120,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: isRecording ? AppTheme.error : AppTheme.accent,
          boxShadow: [
            BoxShadow(
              color: (isRecording ? AppTheme.error : AppTheme.accent)
                  .withOpacity(0.4),
              blurRadius: 20,
              spreadRadius: isRecording ? 10 : 0,
            ),
          ],
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              isRecording ? Icons.mic : Icons.mic_none,
              size: 40,
              color: Colors.white,
            ),
            const SizedBox(height: 8),
            Text(
              isRecording ? '放開發送' : '按住說話',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 14,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _startRecording() async {
    if (_isPressed) return;
    _isPressed = true;

    try {
      await ref.read(audioServiceProvider.notifier).startRecording();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('錄音失敗: $e')),
        );
      }
    }
  }

  Future<void> _stopRecording() async {
    if (!_isPressed) return;
    _isPressed = false;

    await ref.read(audioServiceProvider.notifier).stopRecording();
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add lib/features/voice/voice_input.dart
git commit -m "feat: add push-to-talk voice input button"
```

---

## Chunk 5: Settings Feature

### Task 5.1: Server Settings Page

**Files:**
- Create: `flutter_app/lib/features/settings/server_settings.dart`

- [ ] **Step 1: Create ServerSettings page**

```dart
// lib/features/settings/server_settings.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/constants.dart';
import '../../core/theme.dart';
import '../../data/models/server_config.dart';
import '../../data/services/websocket_service.dart';

/// Server settings page
class ServerSettings extends ConsumerStatefulWidget {
  const ServerSettings({super.key});

  @override
  ConsumerState<ServerSettings> createState() => _ServerSettingsState();
}

class _ServerSettingsState extends ConsumerState<ServerSettings> {
  final _ipController = TextEditingController();
  final _portController = TextEditingController();
  bool _isTesting = false;
  String? _testResult;

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    _ipController.text =
        prefs.getString(PreferenceKeys.serverIp) ?? AppConstants.defaultServerIp;
    _portController.text = (prefs.getInt(PreferenceKeys.serverPort) ??
            AppConstants.defaultServerPort)
        .toString();
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final connectionState = ref.watch(
      websocketServiceProvider.select((s) => s.value?.currentState),
    );

    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '伺服器設定',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 24),
          TextField(
            controller: _ipController,
            decoration: const InputDecoration(
              labelText: '伺服器 IP',
              hintText: '192.168.1.100',
            ),
            keyboardType: TextInputType.number,
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _portController,
            decoration: const InputDecoration(
              labelText: '通訊埠',
              hintText: '8081',
            ),
            keyboardType: TextInputType.number,
          ),
          const SizedBox(height: 24),
          _buildConnectionStatus(connectionState),
          const SizedBox(height: 24),
          Row(
            children: [
              Expanded(
                child: ElevatedButton(
                  onPressed: _isTesting ? null : _testConnection,
                  child: _isTesting
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('測試連線'),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: ElevatedButton(
                  onPressed: _saveSettings,
                  child: const Text('儲存設定'),
                ),
              ),
            ],
          ),
          if (_testResult != null) ...[
            const SizedBox(height: 16),
            Text(
              _testResult!,
              style: TextStyle(
                color: _testResult!.contains('成功')
                    ? AppTheme.success
                    : AppTheme.error,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildConnectionStatus(ConnectionState? state) {
    String statusText;
    Color statusColor;

    switch (state) {
      case ConnectionState.connected:
        statusText = '已連線';
        statusColor = AppTheme.success;
        break;
      case ConnectionState.connecting:
      case ConnectionState.reconnecting:
        statusText = '連線中...';
        statusColor = AppTheme.accent;
        break;
      case ConnectionState.error:
        statusText = '連線錯誤';
        statusColor = AppTheme.error;
        break;
      default:
        statusText = '未連線';
        statusColor = AppTheme.muted;
    }

    return Row(
      children: [
        Container(
          width: 12,
          height: 12,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: statusColor,
          ),
        ),
        const SizedBox(width: 8),
        Text(
          '連線狀態: $statusText',
          style: TextStyle(color: statusColor),
        ),
      ],
    );
  }

  Future<void> _testConnection() async {
    setState(() {
      _isTesting = true;
      _testResult = null;
    });

    try {
      final config = ServerConfig(
        ip: _ipController.text,
        port: int.parse(_portController.text),
      );

      ref.read(serverConfigProvider.notifier).state = config;
      await ref.read(websocketServiceProvider.notifier).connect();

      setState(() {
        _testResult = '連線成功！';
      });
    } catch (e) {
      setState(() {
        _testResult = '連線失敗: $e';
      });
    } finally {
      setState(() {
        _isTesting = false;
      });
    }
  }

  Future<void> _saveSettings() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(PreferenceKeys.serverIp, _ipController.text);
    await prefs.setInt(
      PreferenceKeys.serverPort,
      int.parse(_portController.text),
    );

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('設定已儲存')),
      );
    }
  }

  @override
  void dispose() {
    _ipController.dispose();
    _portController.dispose();
    super.dispose();
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add lib/features/settings/server_settings.dart
git commit -m "feat: add server settings page with connection testing"
```

---

## Chunk 6: Pages and Navigation

### Task 6.1: Main Page

**Files:**
- Create: `flutter_app/lib/pages/main_page.dart`

- [ ] **Step 1: Create MainPage**

```dart
// lib/pages/main_page.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/theme.dart';
import '../data/services/websocket_service.dart';
import '../features/camera/camera_viewer.dart';
import '../features/voice/voice_input.dart';
import '../shared/widgets/status_indicator.dart';

/// Main page with camera view and voice input
class MainPage extends ConsumerStatefulWidget {
  const MainPage({super.key});

  @override
  ConsumerState<MainPage> createState() => _MainPageState();
}

class _MainPageState extends ConsumerState<MainPage> {
  @override
  Widget build(BuildContext context) {
    final connectionState = ref.watch(
      websocketServiceProvider.select((s) => s.value?.currentState),
    );

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // Camera view (takes most of the screen)
            Expanded(
              child: Stack(
                children: [
                  const CameraViewer(),
                  // Status overlay
                  Positioned(
                    top: 8,
                    right: 8,
                    child: StatusIndicator(state: connectionState),
                  ),
                ],
              ),
            ),
            // Bottom control panel
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppTheme.card,
                border: Border(
                  top: BorderSide(color: AppTheme.line),
                ),
              ),
              child: SafeArea(
                top: false,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Voice input button
                    const VoiceInput(),
                    const SizedBox(height: 16),
                    // Instructions
                    Text(
                      connectionState == ConnectionState.connected
                          ? '按住下方按鈕說話'
                          : '請先連接到伺服器',
                      style: TextStyle(
                        color: AppTheme.muted,
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add lib/pages/main_page.dart
git commit -m "feat: add main page with camera viewer and voice input"
```

---

### Task 6.2: Settings Page

**Files:**
- Create: `flutter_app/lib/pages/settings_page.dart`

- [ ] **Step 1: Create SettingsPage**

```dart
// lib/pages/settings_page.dart
import 'package:flutter/material.dart';

import '../core/theme.dart';
import '../features/settings/server_settings.dart';

/// Settings page
class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('設定'),
      ),
      body: const SingleChildScrollView(
        child: ServerSettings(),
      ),
    );
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add lib/pages/settings_page.dart
git commit -m "feat: add settings page"
```

---

### Task 6.3: Shared Widgets

**Files:**
- Create: `flutter_app/lib/shared/widgets/status_indicator.dart`
- Create: `flutter_app/lib/shared/widgets/loading_overlay.dart`

- [ ] **Step 1: Create StatusIndicator**

```dart
// lib/shared/widgets/status_indicator.dart
import 'package:flutter/material.dart';

import '../../core/theme.dart';
import '../../data/services/websocket_service.dart';

/// Connection status indicator badge
class StatusIndicator extends StatelessWidget {
  final ConnectionState? state;

  const StatusIndicator({super.key, this.state});

  @override
  Widget build(BuildContext context) {
    String text;
    Color color;

    switch (state) {
      case ConnectionState.connected:
        text = '已連線';
        color = AppTheme.success;
        break;
      case ConnectionState.connecting:
      case ConnectionState.reconnecting:
        text = '連線中';
        color = AppTheme.accent;
        break;
      case ConnectionState.error:
        text = '錯誤';
        color = AppTheme.error;
        break;
      default:
        text = '離線';
        color = AppTheme.muted;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            text,
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }
}
```

- [ ] **Step 2: Create LoadingOverlay**

```dart
// lib/shared/widgets/loading_overlay.dart
import 'package:flutter/material.dart';

import '../../core/theme.dart';

/// Loading overlay widget
class LoadingOverlay extends StatelessWidget {
  final String? message;

  const LoadingOverlay({super.key, this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black54,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(),
            if (message != null) ...[
              const SizedBox(height: 16),
              Text(
                message!,
                style: TextStyle(
                  color: AppTheme.text,
                  fontSize: 16,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add lib/shared/widgets/
git commit -m "feat: add status indicator and loading overlay widgets"
```

---

### Task 6.4: App Entry Point

**Files:**
- Modify: `flutter_app/lib/main.dart`
- Create: `flutter_app/lib/app.dart`

- [ ] **Step 1: Create app.dart**

```dart
// lib/app.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/theme.dart';
import 'pages/main_page.dart';
import 'pages/settings_page.dart';

/// Main app widget
class VisualImpairmentApp extends StatelessWidget {
  const VisualImpairmentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ProviderScope(
      child: MaterialApp(
        title: '視障輔助',
        theme: AppTheme.dark,
        darkTheme: AppTheme.dark,
        themeMode: ThemeMode.dark,
        home: const MainNavigation(),
      ),
    );
  }
}

/// Bottom navigation with main pages
class MainNavigation extends StatefulWidget {
  const MainNavigation({super.key});

  @override
  State<MainNavigation> createState() => _MainNavigationState();
}

class _MainNavigationState extends State<MainNavigation> {
  int _currentIndex = 0;

  final _pages = const [
    MainPage(),
    SettingsPage(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _pages[_currentIndex],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _currentIndex,
        onDestinationSelected: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: '首頁',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings),
            label: '設定',
          ),
        ],
      ),
    );
  }
}
```

- [ ] **Step 2: Update main.dart**

```dart
// lib/main.dart
import 'package:flutter/material.dart';

import 'app.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const VisualImpairmentApp());
}
```

- [ ] **Step 3: Commit**

```bash
git add lib/main.dart lib/app.dart
git commit -m "feat: add app entry point and navigation"
```

---

## Chunk 7: Final Integration

### Task 7.1: Verify Build

**Files:**
- None (verification task)

- [ ] **Step 1: Run Flutter analyze**

```bash
cd flutter_app
flutter analyze
```

Expected: No errors (warnings acceptable)

- [ ] **Step 2: Build APK (debug)**

```bash
cd flutter_app
flutter build apk --debug
```

Expected: Build successful, APK at `build/app/outputs/flutter-apk/app-debug.apk`

- [ ] **Step 3: Commit final state**

```bash
git add .
git commit -m "feat: Flutter app v1.0.0 complete - camera stream + voice chat"
```

---

### Task 7.2: Update AGENTS.md

**Files:**
- Create: `flutter_app/AGENTS.md`

- [ ] **Step 1: Create AGENTS.md for Flutter app**

```markdown
<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-15 | Updated: 2026-03-15 -->

# flutter_app

## Purpose
Flutter Android 應用程式，連接 FastAPI 伺服器實現攝影機串流和語音對話功能。

## Key Files

| File | Description |
|------|-------------|
| `lib/main.dart` | 應用入口 |
| `lib/app.dart` | MaterialApp + 導航 |
| `lib/core/constants.dart` | API 端點常數 |
| `lib/core/theme.dart` | 深色主題 |
| `lib/data/services/websocket_service.dart` | WebSocket 連接管理 |
| `lib/data/services/camera_stream_service.dart` | 攝影機串流 |
| `lib/data/services/audio_service.dart` | 音頻錄製/播放 |
| `lib/features/camera/camera_viewer.dart` | 影像顯示 |
| `lib/features/voice/voice_input.dart` | 語音輸入 |
| `lib/features/settings/server_settings.dart` | 伺服器設定 |

## For AI Agents

### Working In This Directory
- Flutter SDK 3.x required
- Run `flutter pub get` after dependency changes
- Build: `flutter build apk --debug`
- Run on device: `flutter run`

### Architecture
- State Management: Riverpod
- Communication: WebSocket to FastAPI server
- Camera: camera package + JPEG encoding
- Audio: record (PCM16) + audioplayers

### WebSocket Endpoints
- `/ws/camera` - Send camera frames
- `/ws/viewer` - Receive annotated frames
- `/ws_audio` - Bidirectional audio

## Dependencies

### External
- flutter_riverpod
- web_socket_channel
- camera
- record
- audioplayers
- shared_preferences
- permission_handler

<!-- MANUAL: -->
```

- [ ] **Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs: add AGENTS.md for Flutter app"
```

---

## Summary

| Chunk | Tasks | Description |
|-------|-------|-------------|
| 1 | 1.1-1.3 | Project setup, dependencies, permissions |
| 2 | 2.1-2.3 | Core infrastructure (constants, theme, models, WebSocket) |
| 3 | 3.1-3.2 | Camera feature (service + widget) |
| 4 | 4.1-4.2 | Audio feature (service + widget) |
| 5 | 5.1 | Settings feature |
| 6 | 6.1-6.4 | Pages and navigation |
| 7 | 7.1-7.2 | Final integration and documentation |

**Total Tasks:** 15
**Estimated Time:** 2-3 hours

---

**Plan complete and saved to `docs/superpowers/plans/2026-03-15-flutter-app-implementation.md`. Ready to execute?**
