// lib/screens/splash_screen.dart
// 啟動畫面：自動發現伺服器 → 直接進主畫面（不需登入）

import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:provider/provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter/services.dart';
import '../core/constants.dart';
import '../providers/app_provider.dart';
import '../services/discovery_service.dart';
import 'permission_screen.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  String _status = '啟動中…';

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final app = context.read<AppProvider>();

    // 啟動語音提示（不等待播完，與初始化並行）
    final tts = FlutterTts();
    tts.setLanguage('zh-TW');
    tts.setSpeechRate(0.5);
    tts.speak('正在開啟AI智慧眼鏡APP');

    await app.init();

    // ── 請求必要權限 ────────────────────────────────────────────────────
    _setStatus('請求必要權限…');
    final needsExplain = !(await Permission.phone.isGranted) ||
                         !(await Permission.microphone.isGranted) ||
                         !(await Permission.camera.isGranted) ||
                         !(await Permission.notification.isGranted);
    if (mounted && needsExplain) {
      await Navigator.push(context,
          MaterialPageRoute(builder: (_) => const PermissionScreen()));
    }
    await _requestPermissions();

    // ── 從網站後台讀取 AI 伺服器 URL ─────────────────────────────────
    if (app.websiteUrl.isNotEmpty) {
      _setStatus('從網站後台讀取伺服器設定…');
      final remoteUrl = await app.fetchServerConfigFromWebsite();
      if (remoteUrl != null && remoteUrl.isNotEmpty) {
        _setStatus('套用遠端設定：$remoteUrl');
        final parsed = AppConstants.parseUrl(remoteUrl);
        await app.updateServerSettings(
          parsed.host, parsed.port,
          secure: parsed.secure, baseUrl: remoteUrl,
        );
      }
    }

    // ── 讀取並 TTS 播報 APP 公告 ──────────────────────────────────────
    if (app.websiteUrl.isNotEmpty) {
      _setStatus('讀取公告中…');
      final announcements = await app.fetchAnnouncements();
      for (final ann in announcements) {
        final title = ann['title'] as String? ?? '';
        final body  = ann['body']  as String? ?? '';
        if (title.isNotEmpty || body.isNotEmpty) {
          await app.speak('公告：$title。$body');
          await Future.delayed(const Duration(milliseconds: 3500));
        }
      }
    }

    // ── 連線伺服器 ─────────────────────────────────────────────────────
    // 已有儲存的 baseUrl（公網部署）→ 直接連線，跳過 UDP 區網發現
    if (app.baseUrl.isNotEmpty) {
      _setStatus('連線至 ${app.baseUrl}…');
      final ok = await _tryConnect(app);
      if (mounted) {
        if (ok) {
          await _routeByMode();
        } else {
          // 儲存的公網地址連不上，嘗試區網發現
          _setStatus('公網連線失敗，搜尋區網伺服器…');
          await _discoverAndConnect(app);
        }
      }
    } else {
      // 沒有 baseUrl → 走區網 UDP 發現
      await _discoverAndConnect(app);
    }
  }

  /// 取得儲存的使用者角色
  Future<String> _getUserMode() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('user_mode') ?? 'blind';
  }

  /// 檢查 Android 開發人員模式是否開啟
  Future<bool> _isAndroidDevMode() async {
    try {
      const channel = MethodChannel('com.aiglasses/app_control');
      return await channel.invokeMethod<bool>('isDeveloperMode') ?? false;
    } catch (_) {
      return false;
    }
  }

  /// 區網 UDP 發現 → 連線，失敗則依角色導向（管理員→設定，視障者→客服）
  Future<void> _discoverAndConnect(AppProvider app) async {
    _setStatus('搜尋伺服器中…');
    final result = await DiscoveryService.discover(
      timeout:  const Duration(seconds: 6),
      onStatus: _setStatus,
    );

    if (result != null) {
      await app.updateServerSettings(result.host, result.port);
      _setStatus('連線至 ${result.host}:${result.port}');
      await app.startAllServices();
      if (mounted) await _routeByMode();
    } else {
      _setStatus('使用已儲存設定…');
      await Future.delayed(const Duration(milliseconds: 500));
      final ok = await _tryConnect(app);
      if (mounted) {
        if (ok) {
          await _routeByMode();
        } else {
          await _routeOnFailure();
        }
      }
    }
  }

  Future<void> _requestPermissions() async {
    await [
      Permission.phone,
      Permission.microphone,
      Permission.camera,
      Permission.notification,
    ].request();
  }

  /// 連線成功後依角色路由：開發者→首頁，視障者→盲用畫面
  Future<void> _routeByMode() async {
    if (!mounted) return;
    final mode = await _getUserMode();
    if (!mounted) return;
    Navigator.pushReplacementNamed(
      context,
      mode == 'developer' ? '/home' : '/blind',
    );
  }

  /// 連線失敗後依角色路由
  /// 手機有開 Android 開發人員模式 → 管理員伺服器設定，否則 → 客服聯絡
  Future<void> _routeOnFailure() async {
    if (!mounted) return;
    final isDevMode = await _isAndroidDevMode();
    if (!mounted) return;
    Navigator.pushReplacementNamed(
      context,
      isDevMode ? '/settings' : '/support',
    );
  }

  Future<bool> _tryConnect(AppProvider app) async {
    try {
      final ok = await app.api.healthCheck();
      if (ok) {
        await app.startAllServices();
        return true;
      }
    } catch (_) {}
    return false;
  }

  void _setStatus(String s) {
    if (mounted) setState(() => _status = s);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // ── LOGO ────────────────────────────────────────────────
              const Icon(Icons.visibility, size: 80, color: Colors.white),
              const SizedBox(height: 24),
              const Text(
                'AI 智慧眼鏡',
                style: TextStyle(
                  fontSize: 32,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                '視障輔助導航系統',
                style: TextStyle(fontSize: 16, color: Colors.white54),
              ),
              const SizedBox(height: 40),

              // ── 進度 ────────────────────────────────────────────────
              const SizedBox(
                width: 32,
                height: 32,
                child: CircularProgressIndicator(
                  color: Color(0xFF1565C0),
                  strokeWidth: 2.5,
                ),
              ),
              const SizedBox(height: 20),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 48),
                child: Text(
                  _status,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 16, color: Colors.white70),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
