import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:logger/logger.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../../core/constants.dart';
import '../models/server_config.dart';

/// WebSocket service for managing connections to the FastAPI server.
class WebSocketService {
  final Logger _logger = Logger();

  WebSocketChannel? _cameraChannel;
  WebSocketChannel? _viewerChannel;
  WebSocketChannel? _audioChannel;

  final StreamController<Uint8List> _viewerFrameController =
      StreamController<Uint8List>.broadcast();
  final StreamController<Uint8List> _audioResponseController =
      StreamController<Uint8List>.broadcast();
  final StreamController<String> _transcriptController =
      StreamController<String>.broadcast();
  final StreamController<ConnectionStatus> _connectionStatusController =
      StreamController<ConnectionStatus>.broadcast();

  Stream<Uint8List> get viewerFrames => _viewerFrameController.stream;
  Stream<Uint8List> get audioResponses => _audioResponseController.stream;
  Stream<String> get transcripts => _transcriptController.stream;
  Stream<ConnectionStatus> get connectionStatus => _connectionStatusController.stream;

  ServerConfig _config = const ServerConfig();
  int _reconnectAttempts = 0;
  Timer? _heartbeatTimer;

  /// Update server configuration.
  void updateConfig(ServerConfig config) {
    _config = config;
  }

  /// Connect to all WebSocket endpoints.
  Future<void> connect() async {
    if (_config.serverIp.isEmpty) {
      _logger.e('Server IP is empty');
      _connectionStatusController.add(ConnectionStatus.error);
      return;
    }

    _connectionStatusController.add(ConnectionStatus.connecting);
    _logger.i('Connecting to ${_config.serverIp}:${_config.serverPort}');

    try {
      await _connectViewer();
      await _connectAudio();
      _startHeartbeat();
      _connectionStatusController.add(ConnectionStatus.connected);
      _reconnectAttempts = 0;
      _logger.i('Connected successfully');
    } catch (e) {
      _logger.e('Connection failed: $e');
      _connectionStatusController.add(ConnectionStatus.error);
      _attemptReconnect();
    }
  }

  Future<void> _connectViewer() async {
    final uri = Uri.parse(
      AppConstants.viewerWsPath(_config.serverIp, _config.serverPort),
    );
    _viewerChannel = WebSocketChannel.connect(uri);

    _viewerChannel!.stream.listen(
      (data) {
        if (data is List<int>) {
          _viewerFrameController.add(Uint8List.fromList(data));
        }
      },
      onError: (error) {
        _logger.e('Viewer channel error: $error');
      },
      onDone: () {
        _logger.w('Viewer channel closed');
      },
    );
  }

  Future<void> _connectAudio() async {
    final uri = Uri.parse(
      AppConstants.audioWsPath(_config.serverIp, _config.serverPort),
    );
    _audioChannel = WebSocketChannel.connect(uri);

    _audioChannel!.stream.listen(
      (data) {
        _handleAudioMessage(data);
      },
      onError: (error) {
        _logger.e('Audio channel error: $error');
      },
      onDone: () {
        _logger.w('Audio channel closed');
      },
    );
  }

  void _handleAudioMessage(dynamic data) {
    if (data is List<int>) {
      _audioResponseController.add(Uint8List.fromList(data));
    } else if (data is String) {
      try {
        final json = jsonDecode(data);
        if (json is Map && json.containsKey('transcript')) {
          _transcriptController.add(json['transcript'] as String);
        }
      } catch (_) {
        // Not JSON, treat as plain text transcript
        _transcriptController.add(data);
      }
    }
  }

  void _startHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(AppConstants.heartbeatInterval, (_) {
      _sendHeartbeat();
    });
  }

  void _sendHeartbeat() {
    final heartbeat = jsonEncode({'type': 'ping'});
    _viewerChannel?.sink.add(heartbeat);
    _audioChannel?.sink.add(heartbeat);
  }

  void _attemptReconnect() {
    if (_reconnectAttempts >= AppConstants.maxReconnectAttempts) {
      _logger.e('Max reconnect attempts reached');
      _connectionStatusController.add(ConnectionStatus.error);
      return;
    }

    _reconnectAttempts++;
    _connectionStatusController.add(ConnectionStatus.reconnecting);
    _logger.i('Reconnect attempt $_reconnectAttempts');

    Future.delayed(AppConstants.reconnectDelay, () {
      connect();
    });
  }

  /// Connect camera WebSocket (separate from viewer).
  Future<void> connectCamera() async {
    final uri = Uri.parse(
      AppConstants.cameraWsPath(_config.serverIp, _config.serverPort),
    );
    _cameraChannel = WebSocketChannel.connect(uri);
    _logger.i('Camera channel connected');
  }

  /// Send camera frame to server.
  void sendCameraFrame(Uint8List frameData) {
    _cameraChannel?.sink.add(frameData);
  }

  /// Send audio data to server.
  void sendAudioData(Uint8List audioData) {
    _audioChannel?.sink.add(audioData);
  }

  /// Disconnect all WebSockets.
  void disconnect() {
    _heartbeatTimer?.cancel();
    _cameraChannel?.sink.close();
    _viewerChannel?.sink.close();
    _audioChannel?.sink.close();
    _cameraChannel = null;
    _viewerChannel = null;
    _audioChannel = null;
    _connectionStatusController.add(ConnectionStatus.disconnected);
    _logger.i('Disconnected');
  }

  /// Check if connected.
  bool get isConnected =>
      _viewerChannel != null && _audioChannel != null;

  /// Dispose resources.
  void dispose() {
    disconnect();
    _viewerFrameController.close();
    _audioResponseController.close();
    _transcriptController.close();
    _connectionStatusController.close();
  }
}

/// Provider for WebSocket service.
final webSocketServiceProvider = Provider<WebSocketService>((ref) {
  final service = WebSocketService();
  ref.onDispose(() => service.dispose());
  return service;
});

/// Provider for connection status.
final connectionStatusProvider = StreamProvider<ConnectionStatus>((ref) {
  final service = ref.watch(webSocketServiceProvider);
  return service.connectionStatus;
});

/// Provider for viewer frames.
final viewerFramesProvider = StreamProvider<Uint8List>((ref) {
  final service = ref.watch(webSocketServiceProvider);
  return service.viewerFrames;
});

/// Provider for audio responses.
final audioResponsesProvider = StreamProvider<Uint8List>((ref) {
  final service = ref.watch(webSocketServiceProvider);
  return service.audioResponses;
});

/// Provider for transcripts.
final transcriptsProvider = StreamProvider<String>((ref) {
  final service = ref.watch(webSocketServiceProvider);
  return service.transcripts;
});
