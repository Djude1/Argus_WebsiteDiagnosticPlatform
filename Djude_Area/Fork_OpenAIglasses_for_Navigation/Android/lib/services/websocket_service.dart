// lib/services/websocket_service.dart
// 管理四條 WebSocket 連線：Camera（上行）、Audio（上行）、UI（下行）、IMU（上行）

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:web_socket_channel/io.dart';
import '../core/constants.dart';

/// 工廠：建立 WebSocket（Android only，無 Web build）。
///
/// 不設 pingInterval：實測 5 秒 ping 對 audio/camera binary stream 太激進，
/// server starlette 來不及回 pong 就被 client 強制關閉（close code 1005），
/// 造成連續重連風暴。半關閉偵測改靠 server 端 ws_audio 的 15s frame timeout。
WebSocketChannel _connectWs(String url) => IOWebSocketChannel.connect(url);

typedef FrameCallback = void Function(Uint8List jpeg);

typedef UiMessageCallback = void Function(String message);

class WebSocketService {
  final String host;
  final int    port;
  final bool   secure;
  final String? baseUrl;

  WebSocketService({required this.host, required this.port, this.secure = false, this.baseUrl});

  // ── Camera WS ────────────────────────────────────────────────────────────
  WebSocketChannel?   _cameraWs;
  StreamSubscription? _cameraSub;
  bool _cameraActive = false;

  void connectCamera() {
    _cameraActive = true;
    _doConnectCamera();
  }

  void _doConnectCamera() {
    if (!_cameraActive) return;
    _cameraWs?.sink.close();
    _cameraSub?.cancel();
    _cameraWs = _connectWs(
      AppConstants.wsCamera(host, port, secure: secure, baseUrl: baseUrl),
    );
    // 監聽關閉事件，自動重連
    _cameraSub = _cameraWs!.stream.listen(
      (_) {},
      onError: (_) => _scheduleReconnect(_doConnectCamera),
      onDone:  ()  => _scheduleReconnect(_doConnectCamera),
    );
  }

  /// 送出一幀 JPEG bytes
  void sendFrame(Uint8List jpegBytes) {
    try { _cameraWs?.sink.add(jpegBytes); } catch (_) {}
  }

  void disconnectCamera() {
    _cameraActive = false;
    _cameraSub?.cancel();
    _cameraWs?.sink.close();
    _cameraWs  = null;
    _cameraSub = null;
  }

  // ── Audio WS（PCM16 上行）───────────────────────────────────────────────
  WebSocketChannel?   _audioWs;
  StreamSubscription? _audioWsSub;
  bool _audioWsActive = false;
  bool _bypassWake    = true;   // 預設繞過喚醒詞

  void connectAudio({bool bypassWake = true}) {
    _audioWsActive = true;
    _bypassWake    = bypassWake;
    _doConnectAudio();
  }

  void _doConnectAudio() {
    if (!_audioWsActive) return;
    _audioWs?.sink.close();
    _audioWsSub?.cancel();
    _audioWs = _connectWs(
      AppConstants.wsAudio(host, port, secure: secure, baseUrl: baseUrl),
    );
    // 根據使用者設定決定是否繞過喚醒詞
    final startCmd = _bypassWake ? 'START:BYPASS' : 'START';
    _audioWs!.sink.add(startCmd);
    _audioWsSub = _audioWs!.stream.listen(
      (data) {
        // 處理伺服器回傳的文字指令
        if (data is String) {
          if (data == 'RESTART') {
            // ASR 出錯或逾時，伺服器要求重新啟動，保持相同模式
            try { _audioWs?.sink.add(startCmd); } catch (_) {}
          }
          // OK:STARTED / OK:STOPPED 等確認訊息，目前靜默處理
        }
      },
      onError: (_) => _scheduleReconnect(_doConnectAudio),
      onDone:  ()  => _scheduleReconnect(_doConnectAudio),
    );
  }

  /// 送出 PCM16 資料塊
  void sendAudioChunk(Uint8List pcm16) {
    try { _audioWs?.sink.add(pcm16); } catch (_) {}
  }

  void disconnectAudio() {
    _audioWsActive = false;
    _audioWsSub?.cancel();
    _audioWs?.sink.close();
    _audioWs    = null;
    _audioWsSub = null;
  }

  // ── UI WS（文字下行：ASR / 狀態推播）───────────────────────────────────
  WebSocketChannel?   _uiWs;
  StreamSubscription? _uiSub;
  UiMessageCallback?  onUiMessage;

  void connectUi({UiMessageCallback? onMessage}) {
    onUiMessage = onMessage;
    _uiWs?.sink.close();
    _uiSub?.cancel();
    _uiWs = _connectWs(
      AppConstants.wsUi(host, port, secure: secure, baseUrl: baseUrl),
    );
    _uiSub = _uiWs!.stream.listen(
      (data) {
        if (data is String) onUiMessage?.call(data);
      },
      onError: (_) => _scheduleReconnectUi(onMessage),
      onDone:  () => _scheduleReconnectUi(onMessage),
    );
  }

  void _scheduleReconnectUi(UiMessageCallback? onMessage) {
    Future.delayed(const Duration(seconds: 3), () {
      connectUi(onMessage: onMessage);
    });
  }

  void disconnectUi() {
    _uiSub?.cancel();
    _uiWs?.sink.close();
    _uiWs  = null;
    _uiSub = null;
  }

  // ── IMU WS（JSON 上行）──────────────────────────────────────────────────
  WebSocketChannel?   _imuWs;
  StreamSubscription? _imuSub;
  bool _imuActive = false;

  void connectImu() {
    _imuActive = true;
    _doConnectImu();
  }

  void _doConnectImu() {
    if (!_imuActive) return;
    _imuWs?.sink.close();
    _imuSub?.cancel();
    _imuWs = _connectWs(
      AppConstants.wsImu(host, port, secure: secure, baseUrl: baseUrl),
    );
    _imuSub = _imuWs!.stream.listen(
      (_) {},
      onError: (_) => _scheduleReconnect(_doConnectImu),
      onDone:  ()  => _scheduleReconnect(_doConnectImu),
    );
  }

  void sendImu(Map<String, dynamic> data) {
    try {
      final payload = jsonEncode({
        'accel': {'x': data['ax'] ?? 0, 'y': data['ay'] ?? 0, 'z': data['az'] ?? 0},
        'gyro':  {'x': data['gx'] ?? 0, 'y': data['gy'] ?? 0, 'z': data['gz'] ?? 0},
      });
      _imuWs?.sink.add(payload);
    } catch (_) {}
  }

  void disconnectImu() {
    _imuActive = false;
    _imuSub?.cancel();
    _imuWs?.sink.close();
    _imuWs  = null;
    _imuSub = null;
  }

  // ── 通用重連排程 ──────────────────────────────────────────────────────────
  void _scheduleReconnect(void Function() reconnectFn) {
    Future.delayed(const Duration(seconds: 3), reconnectFn);
  }

  // ── Viewer WS（接收 YOLO 處理後 JPEG，下行）────────────────────────────
  WebSocketChannel?   _viewerWs;
  StreamSubscription? _viewerSub;
  bool _viewerActive = false;
  FrameCallback? _viewerOnFrame;

  void connectViewer({required FrameCallback onFrame}) {
    _viewerOnFrame = onFrame;
    _viewerActive  = true;
    _doConnectViewer();
  }

  void _doConnectViewer() {
    if (!_viewerActive) return;
    _viewerWs?.sink.close();
    _viewerSub?.cancel();
    _viewerWs = _connectWs(
      AppConstants.wsViewer(host, port, secure: secure, baseUrl: baseUrl),
    );
    _viewerSub = _viewerWs!.stream.listen(
      (data) {
        if (data is List<int>) _viewerOnFrame!(Uint8List.fromList(data));
        if (data is Uint8List)  _viewerOnFrame!(data);
      },
      onError: (_) => _scheduleReconnect(_doConnectViewer),
      onDone:  ()  => _scheduleReconnect(_doConnectViewer),
    );
  }

  void disconnectViewer() {
    _viewerActive = false;
    _viewerSub?.cancel();
    _viewerWs?.sink.close();
    _viewerWs     = null;
    _viewerSub    = null;
    _viewerOnFrame = null;
  }

  // ── 全部斷線 ─────────────────────────────────────────────────────────────
  void disconnectAll() {
    disconnectCamera();
    disconnectAudio();
    disconnectUi();
    disconnectImu();
    disconnectViewer();
  }
}
