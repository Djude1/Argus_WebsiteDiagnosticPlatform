// lib/screens/splash_screen.dart
// 啟動畫面：自動發現伺服器 → 直接進主畫面（不需登入）

import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:provider/provider.dart';
import 'package:permission_handler/permission_handler.dart';
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

    // 啟動語音提示
    final tts = FlutterTts();
    await tts.setLanguage('zh-TW');
    await tts.setSpeechRate(0.5);
    await tts.speak('正在開啟AI智慧眼鏡APP');
    Future.delayed(const Duration(seconds: 3), () => tts.stop());

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

    // ── 自動發現伺服器 IP ─────────────────────────────────────────────
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
          Navigator.pushReplacementNamed(context, '/settings');
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

  Future<void> _routeByMode() async {
    if (!mounted) return;
    Navigator.pushReplacementNamed(context, '/blind');
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
