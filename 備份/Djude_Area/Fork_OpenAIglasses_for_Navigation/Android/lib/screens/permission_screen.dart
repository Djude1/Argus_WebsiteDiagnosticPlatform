// lib/screens/permission_screen.dart
// 首次啟動授權說明頁面（視障者友善）
// 以 TTS 語音說明各項權限用途，提供大按鈕一鍵授予

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:permission_handler/permission_handler.dart';

class PermissionScreen extends StatefulWidget {
  const PermissionScreen({super.key});

  @override
  State<PermissionScreen> createState() => _PermissionScreenState();
}

class _PermissionScreenState extends State<PermissionScreen> {
  final FlutterTts _tts = FlutterTts();
  bool _requesting = false;

  // 說明文字
  static const _permissions = [
    _PermInfo(
      icon: Icons.phone,
      title: '撥打電話',
      desc: '緊急時直接撥打求救電話\n無需解鎖手機',
      color: Color(0xFF1A237E),
    ),
    _PermInfo(
      icon: Icons.mic,
      title: '麥克風',
      desc: '語音指令與語音辨識',
      color: Color(0xFF1B5E20),
    ),
    _PermInfo(
      icon: Icons.camera_alt,
      title: '相機',
      desc: '即時環境偵測與盲道導航',
      color: Color(0xFF4A148C),
    ),
    _PermInfo(
      icon: Icons.notifications_active,
      title: '通知',
      desc: '碰撞偵測緊急警報',
      color: Color(0xFF880E4F),
    ),
  ];

  @override
  void initState() {
    super.initState();
    _initTts();
  }

  Future<void> _initTts() async {
    await _tts.setLanguage('zh-TW');
    await _tts.setSpeechRate(0.45);
    await _tts.setVolume(1.0);
    await Future.delayed(const Duration(milliseconds: 600));
    if (!mounted) return;
    await _tts.speak(
      'AI智慧眼鏡需要四項必要權限才能保護您的安全。'
      '撥打電話：緊急時直接撥打求救。'
      '麥克風：語音指令。'
      '相機：盲道導航。'
      '通知：碰撞警報。'
      '請點擊畫面下方的大按鈕授予所有必要權限。',
    );
  }

  @override
  void dispose() {
    _tts.stop();
    super.dispose();
  }

  // ── 逐一請求每個權限，每個前播報說明 ────────────────────────────────────
  Future<void> _grantAll() async {
    if (_requesting) return;
    setState(() => _requesting = true);
    HapticFeedback.heavyImpact();

    final items = [
      (Permission.phone,        '正在請求撥打電話權限'),
      (Permission.microphone,   '正在請求麥克風權限'),
      (Permission.camera,       '正在請求相機權限'),
      (Permission.notification, '正在請求通知權限'),
    ];

    for (final (perm, msg) in items) {
      if (!mounted) break;
      await _tts.speak(msg);
      await Future.delayed(const Duration(milliseconds: 800));
      await perm.request();
    }

    if (!mounted) return;
    await _tts.speak('所有必要權限已設定完成，正在啟動。');
    await Future.delayed(const Duration(milliseconds: 1200));
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onHorizontalDragEnd: (details) {
        if ((details.primaryVelocity ?? 0) > 300) Navigator.pop(context);
      },
      child: Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ── 標題 ──────────────────────────────────────────────────────
            Container(
              color: const Color(0xFF0D0D0D),
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
              child: const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'AI智慧眼鏡 需要以下權限',
                    style: TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.bold,
                        color: Colors.white),
                  ),
                  SizedBox(height: 6),
                  Text(
                    '授予下列權限，確保緊急時能正常使用',
                    style: TextStyle(fontSize: 16, color: Colors.white54),
                  ),
                ],
              ),
            ),

            // ── 四個說明色塊 ──────────────────────────────────────────────
            ...List.generate(_permissions.length, (i) {
              final p = _permissions[i];
              return Expanded(
                child: Semantics(
                  label: '${p.title}：${p.desc.replaceAll('\n', '，')}',
                  child: Container(
                    color: p.color,
                    padding: const EdgeInsets.symmetric(
                        vertical: 12, horizontal: 24),
                    child: Row(
                      children: [
                        Icon(p.icon, size: 40, color: Colors.white70),
                        const SizedBox(width: 18),
                        Expanded(
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                p.title,
                                style: const TextStyle(
                                    fontSize: 22,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.white),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                p.desc,
                                style: const TextStyle(
                                    fontSize: 16, color: Colors.white70),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            }),

            // ── 授予按鈕 ─────────────────────────────────────────────────
            Padding(
              padding: const EdgeInsets.all(16),
              child: Semantics(
                label: '授予所有必要權限，點擊後系統會逐一詢問',
                button: true,
                child: ElevatedButton.icon(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF1565C0),
                    foregroundColor: Colors.white,
                    minimumSize: const Size.fromHeight(80),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16)),
                  ),
                  icon: _requesting
                      ? const SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(
                              color: Colors.white, strokeWidth: 2.5))
                      : const Icon(Icons.check_circle_outline, size: 28),
                  label: Text(
                    _requesting ? '授予中…' : '授予所有必要權限',
                    style: const TextStyle(
                        fontSize: 26, fontWeight: FontWeight.bold),
                  ),
                  onPressed: _requesting ? null : _grantAll,
                ),
              ),
            ),
          ],
        ),
      ),
      ), // Scaffold
    );   // GestureDetector
  }
}

// 資料類
class _PermInfo {
  final IconData icon;
  final String title;
  final String desc;
  final Color color;
  const _PermInfo({
    required this.icon,
    required this.title,
    required this.desc,
    required this.color,
  });
}
