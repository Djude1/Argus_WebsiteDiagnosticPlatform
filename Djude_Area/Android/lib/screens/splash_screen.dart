// lib/screens/splash_screen.dart
// 啟動畫面：自動發現伺服器 → 直接進主畫面（不需登入）

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import '../providers/app_provider.dart';
import '../services/discovery_service.dart';

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
    final auth = context.read<AuthProvider>();
    final app  = context.read<AppProvider>();

    await auth.init();
    await app.init();

    // ── 自動發現伺服器 IP ─────────────────────────────────────────────────
    _setStatus('搜尋伺服器中…');
    final result = await DiscoveryService.discover(
      timeout:  const Duration(seconds: 6),
      onStatus: _setStatus,
    );

    if (result != null) {
      // 找到伺服器，更新設定並啟動服務
      await app.updateServerSettings(result.host, result.port);
      _setStatus('連線至 ${result.host}:${result.port}');
      await app.startAllServices();
      if (mounted) Navigator.pushReplacementNamed(context, '/home');
    } else {
      // 找不到 → 嘗試上次儲存的 IP
      _setStatus('使用上次設定：${app.host}:${app.port}');
      await Future.delayed(const Duration(milliseconds: 800));
      final ok = await _tryConnect(app);
      if (mounted) {
        if (ok) {
          Navigator.pushReplacementNamed(context, '/home');
        } else {
          // 完全找不到 → 進設定頁
          Navigator.pushReplacementNamed(context, '/settings');
        }
      }
    }
  }

  /// 嘗試連線到已儲存的 IP，成功回傳 true（用 /api/health，不需 token）
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
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.visibility, size: 80, color: Colors.white),
            const SizedBox(height: 24),
            const Text(
              'AI 智慧眼鏡',
              style: TextStyle(fontSize: 32, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 32),
            const CircularProgressIndicator(color: Colors.white),
            const SizedBox(height: 20),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 40),
              child: Text(
                _status,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 16, color: Colors.white70),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
