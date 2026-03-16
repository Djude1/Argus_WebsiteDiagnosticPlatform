// lib/providers/app_provider.dart
// 管理伺服器連線、導航狀態、ASR 訊息、緊急連絡人（本機儲存）

import 'dart:async';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:url_launcher/url_launcher.dart';
import '../core/constants.dart';
import '../services/api_service.dart';
import '../services/websocket_service.dart';
import '../services/camera_service.dart';
import '../services/audio_service.dart';
import '../services/imu_service.dart';
import '../services/contacts_service.dart';

class AppProvider extends ChangeNotifier {
  // ── 伺服器設定 ──────────────────────────────────────────────────────────
  String _host   = AppConstants.defaultHost;
  int    _port   = AppConstants.defaultPort;
  bool   _secure = AppConstants.defaultSecure;

  String get host   => _host;
  int    get port   => _port;
  bool   get secure => _secure;

  // ── 服務層 ──────────────────────────────────────────────────────────────
  late ApiService       _api;
  late WebSocketService _ws;
  final CameraService   _camera = CameraService();
  final AudioService    _audio  = AudioService();
  final ImuService      _imu    = ImuService();
  final FlutterTts      _tts    = FlutterTts();

  ApiService get api => _api;

  // ── 連線狀態 ────────────────────────────────────────────────────────────
  bool _connected = false;
  bool get connected => _connected;

  // ── 導航狀態 ────────────────────────────────────────────────────────────
  String _navState = 'IDLE';
  String get navState => _navState;
  String get navStateLabel => AppConstants.stateLabel(_navState);

  // ── 訊息紀錄 ─────────────────────────────────────────────────────────────
  final List<String> _messages = [];
  List<String> get messages => List.unmodifiable(_messages);

  // ── AR Viewer（YOLO 處理後 JPEG 串流）────────────────────────────────────
  final _viewerController = StreamController<Uint8List>.broadcast();
  Stream<Uint8List> get viewerStream => _viewerController.stream;

  void startViewer() {
    _ws.connectViewer(onFrame: (jpeg) => _viewerController.add(jpeg));
  }

  void stopViewer() {
    _ws.disconnectViewer();
  }

  // ── 緊急連絡人（本機 SQLite，不需登入）───────────────────────────────────
  List<Map<String, dynamic>> _contacts = [];
  List<Map<String, dynamic>> get contacts => _contacts;

  // ── 初始化 ──────────────────────────────────────────────────────────────
  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _host   = prefs.getString(AppConstants.keyHost)  ?? AppConstants.defaultHost;
    _port   = prefs.getInt(AppConstants.keyPort)      ?? AppConstants.defaultPort;
    _secure = prefs.getBool(AppConstants.keySecure)   ?? AppConstants.defaultSecure;
    _rebuildServices();

    await _tts.setLanguage('zh-TW');
    await _tts.setSpeechRate(0.5);

    await loadContacts();
    notifyListeners();
  }

  void _rebuildServices() {
    _api = ApiService(host: _host, port: _port, secure: _secure);
    _ws  = WebSocketService(host: _host, port: _port, secure: _secure);
  }

  /// 更新伺服器設定（自動發現或手動設定後呼叫）
  Future<void> updateServerSettings(String host, int port, {bool? secure}) async {
    _host   = host;
    _port   = port;
    _secure = secure ?? _secure;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(AppConstants.keyHost,   host);
    await prefs.setInt(AppConstants.keyPort,       port);
    await prefs.setBool(AppConstants.keySecure,   _secure);
    _rebuildServices();
    notifyListeners();
  }

  // ── 啟動所有串流服務（進入主畫面後呼叫，不需登入）────────────────────────
  Future<void> startAllServices() async {
    if (_connected) return;
    _ws.connectUi(onMessage: _onUiMessage);
    _ws.connectCamera();
    _ws.connectAudio();
    _ws.connectImu();

    await _startCamera();
    await _startMicrophone();
    _imu.start(onData: (d) => _ws.sendImu(d));

    await _audio.startForegroundService();
    _connected = true;
    notifyListeners();

    startPollingNavState();
    _startWatchdog();
  }

  // ── Watchdog：定期確認連線，斷線自動恢復 ─────────────────────────────────
  Timer? _watchdogTimer;

  void _startWatchdog() {
    _watchdogTimer?.cancel();
    _watchdogTimer = Timer.periodic(const Duration(seconds: 10), (_) async {
      if (!_connected) return;
      try {
        await _api.healthCheck();
      } catch (_) {
        // 伺服器連不上：標記斷線，UI 更新
        _connected = false;
        notifyListeners();
        // 5 秒後嘗試重連
        Future.delayed(const Duration(seconds: 5), _reconnect);
      }
    });
  }

  Future<void> _reconnect() async {
    if (_connected) return;
    try {
      await _api.healthCheck();
      // 伺服器回來了，重建所有服務
      _rebuildServices();
      _ws.connectUi(onMessage: _onUiMessage);
      _ws.connectCamera();
      _ws.connectAudio();
      _ws.connectImu();
      // 攝影機和麥克風只在未啟動時重啟
      if (!_camera.isInitialized) await _startCamera();
      if (!_audio.isRecording)    await _startMicrophone();
      _connected = true;
      notifyListeners();
      startPollingNavState();
    } catch (_) {
      // 還沒回來，5 秒後再試
      Future.delayed(const Duration(seconds: 5), _reconnect);
    }
  }

  Future<void> _startCamera() async {
    try {
      await _camera.initialize();
      _camera.startStreaming(onFrame: (b) => _ws.sendFrame(b), fps: 10);
    } catch (e) {
      _addMessage('[系統] 攝影機：$e');
    }
  }

  Future<void> _startMicrophone() async {
    try {
      await _audio.startMicrophone(onChunk: (p) => _ws.sendAudioChunk(p));
    } catch (e) {
      _addMessage('[系統] 麥克風：$e');
    }
  }

  Future<void> stopAllServices() async {
    _watchdogTimer?.cancel();
    _watchdogTimer = null;
    _camera.stopStreaming();
    await _audio.stopMicrophone();
    _imu.stop();
    _ws.disconnectAll();
    await _audio.stopForegroundService();
    stopPollingNavState();
    _connected = false;
    notifyListeners();
  }

  // ── ws_ui 訊息 ────────────────────────────────────────────────────────────
  void _onUiMessage(String msg) {
    _addMessage(msg);
    _checkEmergencyCall(msg);
    if (msg.contains('[狀態]') || msg.contains('[系統]')) _pollNavState();
  }

  void _addMessage(String msg) {
    _messages.add(msg);
    if (_messages.length > 100) _messages.removeAt(0);
    notifyListeners();
  }

  // ── 緊急連絡人（本機）─────────────────────────────────────────────────────
  Future<void> loadContacts() async {
    _contacts = await ContactsService.listContacts();
    notifyListeners();
  }

  Future<void> addContact(String name, String phone) async {
    await ContactsService.addContact(name, phone);
    await loadContacts();
  }

  Future<void> updateContact(int id, String name, String phone) async {
    await ContactsService.updateContact(id, name, phone);
    await loadContacts();
  }

  Future<void> deleteContact(int id) async {
    await ContactsService.deleteContact(id);
    await loadContacts();
  }

  // ── 緊急連絡人語音偵測 ────────────────────────────────────────────────────
  void _checkEmergencyCall(String msg) {
    if (!msg.contains('[ASR]') && !msg.contains('[USER]')) return;
    final lower = msg.toLowerCase();
    for (final c in _contacts) {
      final name = (c['name'] as String).toLowerCase();
      if (lower.contains('打給$name') ||
          lower.contains('聯絡$name') ||
          lower.contains('call $name') ||
          (lower.contains(name) && lower.contains('打電話'))) {
        _initiateCall(c['name'] as String, c['phone'] as String);
        return;
      }
    }
  }

  Future<void> _initiateCall(String name, String phone) async {
    _addMessage('[系統] 撥打給 $name（$phone）');
    await _tts.speak('正在撥打給$name');
    final uri = Uri(scheme: 'tel', path: phone);
    if (await canLaunchUrl(uri)) await launchUrl(uri);
  }

  Future<void> callContact(String name, String phone) =>
      _initiateCall(name, phone);

  // ── 導航控制 ─────────────────────────────────────────────────────────────
  Future<void> startBlindpath() async {
    try { await _api.navBlindpath(); await _tts.speak('開始盲道導航'); }
    catch (e) { _addMessage('[錯誤] $e'); }
  }

  Future<void> startCrossing() async {
    try { await _api.navCrossing(); await _tts.speak('開始過馬路模式'); }
    catch (e) { _addMessage('[錯誤] $e'); }
  }

  Future<void> startTrafficLight() async {
    try { await _api.navTrafficLight(); await _tts.speak('開始紅綠燈偵測'); }
    catch (e) { _addMessage('[錯誤] $e'); }
  }

  Future<void> startItemSearch(String item) async {
    try { await _api.navItemSearch(item); await _tts.speak('開始尋找$item'); }
    catch (e) { _addMessage('[錯誤] $e'); }
  }

  Future<void> stopNavigation() async {
    try { await _api.navStop(); await _tts.speak('已停止導航'); }
    catch (e) { _addMessage('[錯誤] $e'); }
  }

  // ── 輪詢導航狀態 ─────────────────────────────────────────────────────────
  Timer? _stateTimer;

  void startPollingNavState() {
    _stateTimer?.cancel();
    _stateTimer = Timer.periodic(
      const Duration(seconds: 2), (_) => _pollNavState(),
    );
  }

  void stopPollingNavState() {
    _stateTimer?.cancel();
    _stateTimer = null;
  }

  Future<void> _pollNavState() async {
    try {
      final d = await _api.navState();
      final s = d['state'] as String? ?? 'IDLE';
      if (s != _navState) { _navState = s; notifyListeners(); }
    } catch (_) {}
  }

  @override
  void dispose() {
    stopAllServices();
    _tts.stop();
    _viewerController.close();
    super.dispose();
  }
}
