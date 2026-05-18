// lib/providers/app_provider.dart
// 管理伺服器連線、導航狀態、ASR 訊息、緊急連絡人（本機儲存）

import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_tts/flutter_tts.dart';
import '../core/constants.dart';
import 'package:dio/dio.dart' as dio;
import '../services/api_service.dart';
import '../services/call_service.dart';
import '../services/websocket_service.dart';
import '../services/camera_service.dart';
import '../services/audio_service.dart';
import '../services/imu_service.dart';
import '../services/contacts_service.dart';
import '../services/places_service.dart';
import '../services/gps_navigation_service.dart';
import '../services/emergency_notification_service.dart';
import '../services/voice_cache_service.dart';
import '../services/local_voice_service.dart';
import '../screens/emergency_countdown_screen.dart';

class AppProvider extends ChangeNotifier {
  /// 全域 NavigatorKey — 讓 Provider 可在任何頁面 push 倒數畫面（摔倒偵測）
  static final navigatorKey = GlobalKey<NavigatorState>();

  // ── 伺服器設定 ──────────────────────────────────────────────────────────
  String _host         = AppConstants.defaultHost;
  int    _port         = AppConstants.defaultPort;
  bool   _secure       = AppConstants.defaultSecure;
  String _baseUrl      = AppConstants.defaultBaseUrl;
  String _websiteUrl   = '';   // 配置來源網站 URL（Django）
  String _supportPhone = '';   // 客服電話（從 website app-config 讀取）

  String get host         => _host;
  int    get port         => _port;
  bool   get secure       => _secure;
  String get baseUrl      => _baseUrl;
  String get websiteUrl   => _websiteUrl;
  String get supportPhone => _supportPhone;

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

  // ── TTS 設定 ─────────────────────────────────────────────────────────────
  bool   _ttsEnabled    = true;
  double _ttsSpeechRate = 0.5;   // 0.35=慢 / 0.5=正常 / 0.7=快

  bool   get ttsEnabled    => _ttsEnabled;
  double get ttsSpeechRate => _ttsSpeechRate;

  // ── 喚醒詞設定 ─────────────────────────────────────────────────────────────
  // true  → 需要先說「哈囉」才會開始接收語音指令
  // false → 語音直接送 AI 處理（預設關閉喚醒詞）
  bool _wakeWordEnabled = false;
  bool get wakeWordEnabled => _wakeWordEnabled;

  // ── ASR 收音狀態 ───────────────────────────────────────────────────────────
  // "standby"    → 待機中，等待喚醒詞或靜音
  // "listening"  → 正在聆聽使用者的語音指令
  // "processing" → 語音已送出，等待 AI 回應
  String _asrState = 'standby';
  String get asrState => _asrState;
  bool get isListening => _asrState == 'listening';

  // ── ASR 辨識文字追蹤 ──────────────────────────────────────────────────────
  String _asrPartialText = '';          // 即時辨識中的文字
  String get asrPartialText => _asrPartialText;

  final List<String> _asrFinals = [];   // 辨識完成的歷史紀錄（最近 30 筆）
  List<String> get asrFinals => List.unmodifiable(_asrFinals);

  // ── 方位播報模式 ───────────────────────────────────────────────────────────
  // "clock"    → 時鐘方向（如：3點鐘方向）
  // "cardinal" → 前後左右（如：左前方）
  String _positionMode = 'clock';
  String get positionMode => _positionMode;

  Future<void> setTtsEnabled(bool v) async {
    _ttsEnabled = v;
    if (!v) await _tts.stop();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('tts_enabled', v);
    notifyListeners();
  }

  Future<void> setTtsSpeechRate(double rate) async {
    _ttsSpeechRate = rate;
    await _tts.setSpeechRate(rate);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setDouble('tts_speech_rate', rate);
    notifyListeners();
  }

  Future<void> setWakeWordEnabled(bool v) async {
    _wakeWordEnabled = v;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('wake_word_enabled', v);
    // 重新連線音訊 WebSocket，讓伺服器套用新的喚醒詞模式
    if (_connected) {
      _ws.disconnectAudio();
      _ws.connectAudio(bypassWake: !v);
    }
    notifyListeners();
  }

  Future<void> setPositionMode(String mode) async {
    if (mode != 'clock' && mode != 'cardinal') return;
    _positionMode = mode;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('position_mode', mode);
    // 同步通知伺服器（非必要，但能讓語音觸發路徑也即時生效）
    try {
      await _api.setPositionMode(mode);
    } catch (_) {}
    notifyListeners();
  }

  // ── 訊息紀錄 ─────────────────────────────────────────────────────────────
  final List<String> _messages = [];
  List<String> get messages     => List.unmodifiable(_messages);
  int          get messageCount => _messages.length;
  String?      get lastMessage  => _messages.isEmpty ? null : _messages.last;

  /// 偵測 TalkBack 是否開啟
  bool get _isTalkBackOn => WidgetsBinding
      .instance.platformDispatcher.accessibilityFeatures.accessibleNavigation;

  /// 公開語音播報方法（視障者模式 BlindScreen 使用）
  /// TalkBack 開啟時透過 SemanticsService 播報（避免音訊衝突）
  /// TalkBack 關閉時優先播放預載快取，未命中才用 flutter_tts
  Future<void> speak(String text) async {
    if (_isTalkBackOn) {
      SemanticsService.announce(text, TextDirection.ltr);
    } else {
      if (!_ttsEnabled) return;   // 使用者關閉 APP 語音時靜音
      // 優先嘗試快取音檔（延遲更低）
      final hit = await VoiceCacheService.instance.speak(text);
      if (!hit) {
        await _tts.stop();
        await _tts.speak(text);
      }
    }
  }

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

  // ── 儲存地點（本機 SQLite，GPS 導航用）─────────────────────────────────────
  List<Map<String, dynamic>> _places = [];
  List<Map<String, dynamic>> get places => _places;

  // ── 初始化 ──────────────────────────────────────────────────────────────
  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _host       = prefs.getString(AppConstants.keyHost)       ?? AppConstants.defaultHost;
    _port       = prefs.getInt(AppConstants.keyPort)          ?? AppConstants.defaultPort;
    _secure     = prefs.getBool(AppConstants.keySecure)       ?? AppConstants.defaultSecure;
    _baseUrl    = prefs.getString(AppConstants.keyBaseUrl)    ?? AppConstants.defaultBaseUrl;
    _websiteUrl = prefs.getString(AppConstants.keyWebsiteUrl) ?? '';
    _rebuildServices();

    _ttsEnabled      = prefs.getBool('tts_enabled')        ?? true;
    _ttsSpeechRate   = prefs.getDouble('tts_speech_rate') ?? 0.5;
    _positionMode    = prefs.getString('position_mode')   ?? 'clock';
    _wakeWordEnabled = prefs.getBool('wake_word_enabled') ?? false;

    await _tts.setLanguage('zh-TW');
    await _tts.setSpeechRate(_ttsSpeechRate);

    // 背景預載固定語音快取（不阻塞啟動流程）
    VoiceCacheService.instance.init(_tts);
    LocalVoiceService.instance.init(); // 載入 assets/voice_map.json

    await loadContacts();
    await loadPlaces();
    notifyListeners();
  }

  void _rebuildServices() {
    _api = ApiService(host: _host, port: _port, secure: _secure, baseUrl: _baseUrl);
    _ws  = WebSocketService(host: _host, port: _port, secure: _secure, baseUrl: _baseUrl);
  }

  /// 更新配置來源網站 URL（Django Website）
  Future<void> updateWebsiteUrl(String url) async {
    _websiteUrl = url;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(AppConstants.keyWebsiteUrl, url);
    notifyListeners();
  }

  // ── APP 公告 ─────────────────────────────────────────────────────────────────
  List<Map<String, dynamic>> _announcements = [];
  List<Map<String, dynamic>> get announcements => List.unmodifiable(_announcements);

  /// 從網站後台讀取有效 APP 公告，成功時回傳列表，失敗靜默回傳空列表
  Future<List<Map<String, dynamic>>> fetchAnnouncements() async {
    if (_websiteUrl.isEmpty) return [];
    try {
      final endpoint =
          '${_websiteUrl.replaceAll(RegExp(r'/+$'), '')}/api/content/announcements/';
      final client = dio.Dio(dio.BaseOptions(
        connectTimeout: const Duration(seconds: 8),
        receiveTimeout: const Duration(seconds: 8),
      ));
      final resp = await client.get(endpoint);
      final raw  = resp.data;
      final list = ((raw is Map<String, dynamic>
                      ? raw['announcements'] as List<dynamic>?
                      : null) ?? [])
          .whereType<Map<String, dynamic>>()
          .toList();
      _announcements = list;
      notifyListeners();
      return list;
    } catch (_) {
      return [];
    }
  }

  /// 從網站後台讀取 AI 伺服器 URL 與客服電話，成功時回傳 server_url 字串，失敗回傳 null
  Future<String?> fetchServerConfigFromWebsite() async {
    if (_websiteUrl.isEmpty) return null;
    try {
      final endpoint =
          '${_websiteUrl.replaceAll(RegExp(r'/+$'), '')}/api/content/app-config/';
      final client = dio.Dio(dio.BaseOptions(
        connectTimeout: const Duration(seconds: 8),
        receiveTimeout: const Duration(seconds: 8),
      ));
      final resp = await client.get(endpoint);
      final data = resp.data as Map<String, dynamic>;
      final serverUrl = data['server_url'] as String? ?? '';
      // 同步讀取客服電話（後台未設定時為空字串）
      _supportPhone = data['support_phone'] as String? ?? '';
      notifyListeners();
      return serverUrl.isNotEmpty ? serverUrl : null;
    } catch (_) {
      return null;
    }
  }

  /// 更新伺服器設定（支援完整 URL 或 host+port）
  Future<void> updateServerSettings(String host, int port, {bool? secure, String? baseUrl}) async {
    final wasConnected = _connected;

    // 切換裝置前先停止所有串流，避免相機 callback 繼續把影格送往舊裝置
    if (wasConnected) {
      _watchdogTimer?.cancel();
      _watchdogTimer = null;
      _camera.stopStreaming();
      await _audio.stopMicrophone();
      _imu.stop();
      _ws.disconnectAll();
      stopPollingNavState();
      _connected = false;
    }

    _host    = host;
    _port    = port;
    _secure  = secure ?? _secure;
    _baseUrl = baseUrl ?? _baseUrl;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(AppConstants.keyHost,    host);
    await prefs.setInt(AppConstants.keyPort,       port);
    await prefs.setBool(AppConstants.keySecure,    _secure);
    await prefs.setString(AppConstants.keyBaseUrl, _baseUrl);
    _rebuildServices();

    // 若原本已連線，切換完成後重新啟動所有服務（camera callback 正確綁定新裝置）
    if (wasConnected) {
      await startAllServices();
    }

    notifyListeners();
  }

  // ── 裝置感測器設定（固定預設值）──────────────────────────────────────────
  final double _impactThreshold = 30.0;   // m/s²，預設 3G
  // 冷卻 10 秒：擋同一次摔倒的重複觸發，但倒數結束後會立即 resetCooldown()
  final int    _cooldownSeconds = 10;

  double get impactThreshold => _impactThreshold;
  int    get cooldownSeconds  => _cooldownSeconds;

  // ── 文件閱讀（暫停 / 恢復相機串流）─────────────────────────────────────
  /// 進入文件閱讀頁前呼叫：停止導航相機，釋放給閱讀功能使用
  Future<void> pauseCameraStreaming() async {
    _camera.stopStreaming();
  }

  /// 離開文件閱讀頁後呼叫：重新啟動導航相機串流
  Future<void> resumeCameraStreaming() async {
    if (_connected) await _startCamera();
  }

  /// 傳送圖片給伺服器 Gemini OCR，回傳 { text, char_count }
  Future<Map<String, dynamic>> readDocument(String imageBase64) async {
    return await _api.readDocument(imageBase64);
  }

  /// 傳送文件全文 + 問題，回傳 { answer }
  Future<Map<String, dynamic>> explainDocument(String text, String question) async {
    return await _api.explainDocument(text, question);
  }

  // ── 背景撞擊偵測狀態 ─────────────────────────────────────────────────────
  bool   _appInForeground        = true;
  /// 背景偵測到的撞擊力道，等使用者點通知回到前台後補彈倒數畫面
  double _pendingImpactMagnitude = 0.0;

  /// App 前台/背景狀態切換（由 BlindScreen 的 WidgetsBindingObserver 呼叫）
  void handleLifecycleState(AppLifecycleState state) {
    _appInForeground = (state == AppLifecycleState.resumed);
    if (_appInForeground && _pendingImpactMagnitude > 0) {
      // App 回到前台：取消系統通知，補彈倒數畫面
      EmergencyNotificationService().cancelFallAlert();
      final m = _pendingImpactMagnitude;
      _pendingImpactMagnitude = 0.0;
      _showImpactCountdown(m);
    }
  }

  /// IMU 撞擊回呼：Provider 層統一處理，任何頁面都會觸發
  void _onImpactDetected(double magnitude) {
    debugPrint('[IMPACT-DEBUG] _onImpactDetected 收到事件 '
        'magnitude=${magnitude.toStringAsFixed(1)} '
        'contacts=${_contacts.length} '
        'foreground=$_appInForeground');
    if (_contacts.isEmpty) {
      // 無緊急連絡人，僅記錄（no-op），不觸發倒數
      debugPrint('[IMPACT-DEBUG] contacts 為空，直接 return，不彈倒數');
      reportImpactEvent(magnitude, 'no_contacts');
      return;
    }
    if (_appInForeground) {
      debugPrint('[IMPACT-DEBUG] 前台 → 透過 navigatorKey push 倒數畫面');
      _showImpactCountdown(magnitude);
    } else {
      // 背景：先存待辦量，發系統通知；回前台時 handleLifecycleState 會補彈
      debugPrint('[IMPACT-DEBUG] 背景 → 顯示系統通知，等回前台補彈');
      _pendingImpactMagnitude = magnitude;
      EmergencyNotificationService().showFallAlert(magnitude);
    }
  }

  /// 用全域 NavigatorKey push 倒數畫面，不受當前頁面是 Blind/Home/Settings 影響
  void _showImpactCountdown(double magnitude) {
    final nav = navigatorKey.currentState;
    debugPrint('[IMPACT-DEBUG] _showImpactCountdown navigatorKey.currentState=${nav == null ? "NULL" : "OK"}');
    if (nav == null) return;
    nav.push(MaterialPageRoute(
      builder: (_) => EmergencyCountdownScreen(
        magnitude: magnitude,
        onOutcome: (outcome) => _afterImpactCountdown(magnitude, outcome),
      ),
    ));
    debugPrint('[IMPACT-DEBUG] 倒數畫面已 push');
  }

  /// 倒數結束後彈誤判詢問 dialog，再把結果回報伺服器
  Future<void> _afterImpactCountdown(double magnitude, String outcome) async {
    debugPrint('[IMPACT-DEBUG] _afterImpactCountdown outcome=$outcome');
    // 倒數結束（取消或自動撥出）→ 立即重置冷卻，下次撞擊立刻可再觸發
    _imu.resetCooldown();
    // 等畫面回到原本所在頁面後再彈 dialog
    await Future.delayed(const Duration(milliseconds: 400));
    final ctx = navigatorKey.currentContext;
    if (ctx == null) return;

    final isFalse = await showDialog<bool>(
      // ignore: use_build_context_synchronously
      context: ctx,
      barrierDismissible: false,
      builder: (dialogCtx) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A2E),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Text(
          '這次偵測是誤判嗎？',
          style: TextStyle(
              fontSize: 20, fontWeight: FontWeight.bold, color: Colors.white),
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '撞擊力道：${magnitude.toStringAsFixed(1)} m/s²',
              style: const TextStyle(fontSize: 14, color: Colors.white54),
            ),
            const SizedBox(height: 8),
            const Text(
              '您的回饋將幫助我們調整偵測靈敏度。',
              style: TextStyle(fontSize: 14, color: Colors.white70),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx, true),
            child: const Text('是，這是誤判',
                style: TextStyle(color: Colors.orangeAccent, fontSize: 16)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF1B5E20),
            ),
            onPressed: () => Navigator.pop(dialogCtx, false),
            child: const Text('不是，真的摔倒了',
                style: TextStyle(color: Colors.white, fontSize: 16)),
          ),
        ],
      ),
    );

    if (isFalse == null) return;
    reportImpactEvent(magnitude, outcome, isFalsePositive: isFalse);
    await speak(isFalse ? '已記錄為誤判，感謝回饋' : '已記錄，請注意安全');
  }

  // ── 回報撞擊事件（含使用者誤判回饋）────────────────────────────────────────
  /// [outcome]：auto_dialed / cancelled
  /// [isFalsePositive]：使用者回報是否為誤判（預設 false）
  /// 回傳至 Website 後台（Django），不走 AI 伺服器
  Future<void> reportImpactEvent(double magnitude, String outcome,
      {bool isFalsePositive = false, String note = ''}) async {
    if (_websiteUrl.isEmpty) return;
    try {
      final d = dio.Dio(dio.BaseOptions(
        baseUrl: _websiteUrl.replaceAll(RegExp(r'/+$'), ''),
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 10),
      ));
      await d.post('/api/content/impact-feedback/', data: {
        'magnitude':          magnitude,
        'outcome':            outcome,
        'is_false_positive':  isFalsePositive,
        'note':               note,
      });
    } catch (_) {
      // 回報失敗不影響主流程
    }
  }

  // ── 啟動所有串流服務（進入主畫面後呼叫，不需登入）────────────────────────
  Future<void> startAllServices() async {
    if (_connected) return;
    _ws.connectUi(onMessage: _onUiMessage);
    _ws.connectCamera();
    _ws.connectAudio(bypassWake: !_wakeWordEnabled);
    _ws.connectImu();

    await _startCamera();
    _imu.start(onData: (d) => _ws.sendImu(d));

    // 重置伺服器導航狀態：僅在伺服器確實有導航在運行時才發送停止指令，避免廣播無謂的錯誤訊息
    try {
      final stateResp = await _api.navState();
      final serverState = stateResp['state'] as String? ?? 'IDLE';
      if (!['IDLE', 'CHAT', '', 'unavailable'].contains(serverState)) {
        await _api.navStop();
      }
    } catch (_) {}
    _navState = 'IDLE';

    // 套用設定並啟動撞擊偵測（App 層級，前後台均有效）
    _imu.configure(
      impactThreshold: _impactThreshold,
      cooldownSeconds: _cooldownSeconds,
    );
    _imu.startImpactDetection(onImpact: _onImpactDetected);

    await _audio.startForegroundService();
    // 播放伺服器 TTS 串流（/stream.wav），行為與 ESP32 喇叭相同
    // ignore: unawaited_futures
    _audio.playStreamWav(_host, _port, secure: _secure, baseUrl: _baseUrl);
    _connected = true;
    _addMessage('[版本] APP 2026-05-13 ASR 修復版 — chip+filter+ping+寬鬆 nav');
    _addMessage('[系統] 已連線 SERVER → ${_endpointLabel()}');
    notifyListeners();

    startPollingNavState();
    _startWatchdog();

    // 麥克風立即啟動（使用者要求一進入 APP 就收音）
    // 注意：splash 階段的歡迎 TTS 可能被錄到，使用者已知此限制
    await _startMicrophone();
  }

  /// 構造目前 server 端點字串（baseUrl 優先，否則回 host:port）
  String _endpointLabel() {
    final base = _baseUrl.trim();
    if (base.isNotEmpty) return base;
    return '$_host:$_port';
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
      _ws.connectAudio(bypassWake: !_wakeWordEnabled);
      _ws.connectImu();
      // 攝影機和麥克風只在未啟動時重啟
      if (!_camera.isInitialized) await _startCamera();
      if (!_audio.isRecording)    await _startMicrophone();
      // ignore: unawaited_futures
      _audio.playStreamWav(_host, _port, secure: _secure, baseUrl: _baseUrl);
      _connected = true;
      _addMessage('[系統] 重新連線 SERVER → ${_endpointLabel()}');
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

  /// 麥克風是否正在錄音（開發者音訊測試用）
  bool get isRecordingMic => _audio.isRecording;

  /// 測試播放伺服器 TTS 音訊串流（/stream.wav）
  Future<void> playServerAudioTest() async {
    try {
      await _audio.playStreamWav(_host, _port, secure: _secure,
          baseUrl: _baseUrl.isNotEmpty ? _baseUrl : null);
    } catch (e) {
      _addMessage('[錯誤] 音訊串流播放失敗：$e');
    }
  }

  Future<void> stopAllServices() async {
    _watchdogTimer?.cancel();
    _watchdogTimer = null;
    _camera.stopStreaming();
    await _audio.stopMicrophone();
    await _audio.stopPlayback();
    _imu.stop();
    _ws.disconnectAll();
    await _audio.stopForegroundService();
    stopPollingNavState();
    _connected = false;
    _asrState = 'standby';
    _asrPartialText = '';
    _asrFinals.clear();
    notifyListeners();
  }

  // ── ws_ui 訊息 ────────────────────────────────────────────────────────────
  void _onUiMessage(String msg) {
    // NAV_STATE: 推送：伺服器狀態變更時直接送達，無需輪詢（0ms 延遲）
    if (msg.startsWith('NAV_STATE:')) {
      final s = msg.substring(10);
      if (s != _navState) {
        _navState = s;
        // 導航狀態變更表示指令已處理完畢，ASR 回到待機
        if (_asrState == 'processing') {
          _asrState = 'standby';
        }
        notifyListeners();
      }
      return;
    }
    // 伺服器每 30 秒發送的保活訊號，不顯示在訊息記錄中
    if (msg == 'PING') return;

    // INIT: WebSocket 連線時伺服器推送初始 ASR 狀態
    if (msg.startsWith('INIT:')) {
      try {
        final payload = jsonDecode(msg.substring(5)) as Map<String, dynamic>;
        _asrPartialText = (payload['partial'] as String?) ?? '';
        final finals = payload['finals'] as List?;
        if (finals != null) {
          _asrFinals.clear();
          _asrFinals.addAll(finals.map((e) => e.toString()));
        }
        notifyListeners();
      } catch (_) {}
      return;
    }

    // SPEAK: 本地語音播放（伺服器命中預錄 WAV 時推送）
    // 格式：SPEAK:{"text":"請向左平移","duration_ms":1640}
    if (msg.startsWith('SPEAK:')) {
      _handleSpeakMessage(msg.substring(6));
      return;
    }

    // PARTIAL: 語音正在辨識中 → ASR 進入聆聽狀態
    // 旁路模式下伺服器不推 SPEAK:開始對話，需靠 PARTIAL 偵測
    // [ 開頭的 partial 是 server 廣播 stream（[AI]/[系统]/[导航] 等）
    //   [AI] → 強制切 processing 並顯示 AI 回覆（不論先前狀態為何，重設 15s timer）
    //   其他廣播 → 不切狀態，僅在 processing 期間更新 chip 文字
    if (msg.startsWith('PARTIAL:')) {
      final partialText = msg.substring(8).trim();
      final isServerBroadcast = partialText.startsWith('[');
      if (isServerBroadcast) {
        final stripped = partialText.replaceFirst(RegExp(r'^\[[^\]]+\]\s*'), '');
        if (partialText.startsWith('[AI]') && stripped.isNotEmpty) {
          _asrPartialText = stripped;
          _updateAsrState('processing');   // 強切 processing，重設 15s timer
        } else if (_asrState == 'processing' && stripped.isNotEmpty) {
          _asrPartialText = stripped;
          notifyListeners();
        }
      } else {
        _asrPartialText = partialText;
        if (partialText.isNotEmpty && partialText != '（已開始接收音訊…）') {
          _updateAsrState('listening');
          _resetListeningTimeout();   // 每次新 partial 都重置 5 秒超時
        }
      }
      notifyListeners();
    }

    // FINAL: server 端的 ui_broadcast_final 同時被「ASR 真實語音 final」和
    // 「[系統]/[导航]/[AI]/[狀態]/[錯誤] 等廣播訊息」共用。
    // 使用者真實語音 final 不會以 [ 開頭；[AI] 前綴強切 processing；
    // 其他 [xxx] 不切狀態僅更新 chip。
    if (msg.startsWith('FINAL:')) {
      final finalText = msg.substring(6).trim();
      final isServerBroadcast = finalText.startsWith('[');
      if (!isServerBroadcast) {
        if (finalText.isNotEmpty) {
          _asrFinals.add(finalText);
          if (_asrFinals.length > 30) _asrFinals.removeAt(0);
        }
        _asrPartialText = '';
        _updateAsrState('processing');
      } else {
        final stripped = finalText.replaceFirst(RegExp(r'^\[[^\]]+\]\s*'), '');
        if (finalText.startsWith('[AI]') && stripped.isNotEmpty) {
          _asrPartialText = stripped;
          _updateAsrState('processing');   // 強切 processing，重設 15s timer
        } else if (_asrState == 'processing' && stripped.isNotEmpty) {
          _asrPartialText = stripped;
        }
      }
      notifyListeners();
    }

    _addMessage(msg);
    _checkEmergencyCall(msg);
  }

  void _handleSpeakMessage(String jsonStr) {
    try {
      final data       = jsonDecode(jsonStr) as Map<String, dynamic>;
      final text       = data['text']        as String? ?? '';
      final durationMs = (data['duration_ms'] as num?)?.toInt() ?? 2000;
      if (text.isEmpty) return;

      // 追蹤 ASR 音效，更新收音狀態
      if (text == '開始對話') {
        _updateAsrState('listening');
      } else if (text == '結束收音') {
        _updateAsrState('standby');
      }

      // 非同步：本地 WAV 優先，stream 靜音；未命中則放行 stream
      LocalVoiceService.instance.speak(text).then((playedMs) {
        if (playedMs != null) {
          // 命中本地 WAV：靜音 /stream.wav 避免重播
          _audio.suppressStreamFor(durationMs);
        }
        // 未命中：/stream.wav 繼續正常播放（伺服器已發出音訊）
      });
    } catch (e) {
      debugPrint('[AppProvider] SPEAK 解析失敗: $e');
    }
  }

  Timer? _asrProcessingTimer;
  Timer? _asrListeningTimer;

  /// 重置 listening 超時：每收到新 partial 就重新計時 5 秒，
  /// 避免 server 沒推 final / SPEAK:結束收音 時 chip 永遠卡「聆聽中」
  void _resetListeningTimeout() {
    _asrListeningTimer?.cancel();
    _asrListeningTimer = Timer(const Duration(seconds: 5), () {
      if (_asrState == 'listening') {
        _asrState = 'standby';
        _asrPartialText = '';
        debugPrint('[AppProvider] listening 5 秒無新 partial → 回 standby');
        notifyListeners();
      }
    });
  }

  void _updateAsrState(String newState) {
    if (_asrState != newState) {
      _asrState = newState;
      debugPrint('[AppProvider] ASR 狀態: $_asrState');

      // 任何狀態切換都清空兩個 timer，下面只重設當前狀態需要的
      _asrProcessingTimer?.cancel();
      _asrListeningTimer?.cancel();

      // processing 狀態設定 15 秒超時，自動回到 standby
      // 避免 Omni 對話等不推送 NAV_STATE 的場景卡在 processing
      if (newState == 'processing') {
        _asrProcessingTimer = Timer(const Duration(seconds: 15), () {
          if (_asrState == 'processing') {
            _asrState = 'standby';
            debugPrint('[AppProvider] ASR 超時回到 standby');
            notifyListeners();
          }
        });
      }

      notifyListeners();
    }
  }

  void _addMessage(String msg) {
    _messages.add(msg);
    if (_messages.length > 100) _messages.removeAt(0);
    notifyListeners();
  }

  /// 公開方法：讓各畫面寫入 DEBUG 訊息記錄
  void addDebugMessage(String msg) => _addMessage(msg);

  // ── 緊急連絡人（本機）─────────────────────────────────────────────────────
  Future<void> loadContacts() async {
    _contacts = await ContactsService.listContacts();
    notifyListeners();
  }

  Future<void> addContact(String name, String phone) async {
    if (_contacts.length >= 2) return; // 最多 2 位
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

  // ── 儲存地點（本機 SQLite）─────────────────────────────────────────────────
  Future<void> loadPlaces() async {
    _places = await PlacesService.listPlaces();
    notifyListeners();
  }

  Future<void> addPlace({
    required String name,
    String address = '',
    double latitude = 0,
    double longitude = 0,
    String category = 'other',
  }) async {
    await PlacesService.addPlace(
      name: name, address: address,
      latitude: latitude, longitude: longitude,
      category: category,
    );
    await loadPlaces();
  }

  Future<void> updatePlace(int id, {
    required String name,
    String address = '',
    double latitude = 0,
    double longitude = 0,
    String category = 'other',
  }) async {
    await PlacesService.updatePlace(id,
      name: name, address: address,
      latitude: latitude, longitude: longitude,
      category: category,
    );
    await loadPlaces();
  }

  Future<void> deletePlace(int id) async {
    await PlacesService.deletePlace(id);
    await loadPlaces();
  }

  // ── 緊急連絡人語音偵測 ────────────────────────────────────────────────────
  void _checkEmergencyCall(String msg) {
    // 伺服器廣播的 ASR 原始文字格式為 "FINAL:使用者說的話"
    // 也相容 [ASR] / [USER] 前綴的舊格式
    final bool isUserSpeech = msg.startsWith('FINAL:') ||
        msg.contains('[ASR]') ||
        msg.contains('[USER]');
    if (!isUserSpeech) return;

    // 去掉 FINAL: 前綴後再比對，避免前綴干擾中文比對
    final text  = msg.startsWith('FINAL:') ? msg.substring(6) : msg;
    final lower = text.toLowerCase();

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
    await speak('正在撥打給$name');   // 語音指令自動觸發，非按鈕，保留語音
    await CallService.call(phone);
  }

  Future<void> callContact(String name, String phone) =>
      _initiateCall(name, phone);

  // ── 導航控制（按鈕觸發，TalkBack 開啟時跳過 TTS，由狀態變化語音覆蓋）──────
  Future<void> startBlindpath() async {
    try {
      await _api.navBlindpath();
      // 立即更新本地狀態，避免使用者重複點擊造成競爭條件
      _navState = 'BLINDPATH_NAV';
      notifyListeners();
      if (!_isTalkBackOn) _tts.speak('開始避障導航');
    } catch (e) { _addMessage('[錯誤] $e'); }
  }

  Future<void> startCrossing() async {
    try {
      await _api.navCrossing();
      // 立即更新本地狀態
      _navState = 'CROSSING';
      notifyListeners();
      if (!_isTalkBackOn) _tts.speak('開始過馬路模式');
    } catch (e) { _addMessage('[錯誤] $e'); }
  }

  Future<void> startTrafficLight() async {
    try {
      await _api.navTrafficLight();
      // 立即更新本地狀態
      _navState = 'TRAFFIC_LIGHT_DETECTION';
      notifyListeners();
      if (!_isTalkBackOn) _tts.speak('開始紅綠燈偵測');
    } catch (e) { _addMessage('[錯誤] $e'); }
  }

  Future<void> startItemSearch(String item) async {
    try {
      await _api.navItemSearch(item, positionMode: _positionMode);
      // 立即更新本地狀態
      _navState = 'ITEM_SEARCH';
      notifyListeners();
      if (!_isTalkBackOn) _tts.speak('開始尋找$item');
    } catch (e) { _addMessage('[錯誤] $e'); }
  }

  /// 停止所有功能（GPS + 伺服器避障）
  Future<void> stopNavigation() async {
    try {
      GpsNavigationService.instance.stopNavigation();
      _gpsNavActive = false;
      _gpsDistance = double.infinity;
      await _api.navStop();
      _navState = 'IDLE';
      notifyListeners();
      if (!_isTalkBackOn) _tts.speak('已停止所有功能');
    } catch (e) { _addMessage('[錯誤] $e'); }
  }

  /// 只停止 GPS 導航（保留伺服器端避障）
  Future<void> stopGpsNavigation() async {
    try {
      GpsNavigationService.instance.stopNavigation();
      _gpsNavActive = false;
      _gpsDistance = double.infinity;
      notifyListeners();
      if (!_isTalkBackOn) _tts.speak('已停止導航，避障功能繼續運作');
    } catch (e) { _addMessage('[錯誤] $e'); }
  }

  /// 只停止伺服器端避障（保留 GPS 導航）
  Future<void> stopObstacleAvoidance() async {
    try {
      await _api.navStop();
      _navState = 'IDLE';
      notifyListeners();
      if (!_isTalkBackOn) _tts.speak('已停止避障');
    } catch (e) { _addMessage('[錯誤] $e'); }
  }

  // ── GPS 導航（背景 Google Maps + 前景避障）──────────────────────────────
  bool _gpsNavActive = false;
  bool get gpsNavActive => _gpsNavActive;
  double _gpsDistance = double.infinity;
  double get gpsDistance => _gpsDistance;

  /// 啟動 GPS 導航：背景 Google Maps 語音 + GPS 距離監測
  /// 避障功能需使用者自行開啟（獨立控制）
  Future<void> startGpsNavigation(Map<String, dynamic> place) async {
    final lat = (place['latitude'] as num?)?.toDouble() ?? 0;
    final lng = (place['longitude'] as num?)?.toDouble() ?? 0;
    final name = place['name'] as String? ?? '目的地';

    if (lat == 0 && lng == 0) {
      speak('此地點沒有座標，無法啟動導航。請編輯地點填入地址');
      return;
    }

    // 1. 啟動 GPS 導航（背景 Google Maps + 距離監測）
    _gpsNavActive = true;
    _gpsDistance = double.infinity;
    notifyListeners();

    final success = await GpsNavigationService.instance.startNavigation(
      latitude: lat,
      longitude: lng,
      name: name,
      onStateChanged: _onGpsStateChanged,
    );

    if (success) {
      // 2. 同時啟動避障（讓使用者一邊聽 Google Maps 語音一邊避障）
      await startBlindpath();
      speak('前往$name，導航與避障已啟動。Google Maps 語音將在背景引導路線');
    } else {
      speak('GPS 啟動失敗，請確認已開啟定位權限');
      _gpsNavActive = false;
      notifyListeners();
    }
  }

  /// GPS 狀態變更回呼
  void _onGpsStateChanged(GpsNavState gpsState, double distance) {
    _gpsDistance = distance;

    switch (gpsState) {
      case GpsNavState.arriving:
        speak('即將到達${GpsNavigationService.instance.destName}，剩餘${distance.toStringAsFixed(0)}公尺');
        break;
      case GpsNavState.arrived:
        speak('已到達${GpsNavigationService.instance.destName}，導航結束，避障功能繼續運作');
        // 到達後只停 GPS 導航，保留避障
        Future.delayed(const Duration(seconds: 2), () => stopGpsNavigation());
        break;
      default:
        break;
    }
    notifyListeners();
  }

  // ── 輪詢導航狀態 ─────────────────────────────────────────────────────────
  Timer? _stateTimer;

  void startPollingNavState() {
    _stateTimer?.cancel();
    // 10 秒備援輪詢（主要靠 NAV_STATE: WebSocket 推送即時更新）
    _stateTimer = Timer.periodic(
      const Duration(seconds: 10), (_) => _pollNavState(),
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
    _asrProcessingTimer?.cancel();
    _asrListeningTimer?.cancel();
    stopAllServices();
    _tts.stop();
    _viewerController.close();
    super.dispose();
  }
}
