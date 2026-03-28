// lib/screens/mode_select_screen.dart
// 首次啟動模式選擇：視障者模式 or 開發者模式
// 選擇後儲存至 SharedPreferences，下次啟動直接跳過

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ModeSelectScreen extends StatefulWidget {
  const ModeSelectScreen({super.key});

  @override
  State<ModeSelectScreen> createState() => _ModeSelectScreenState();
}

class _ModeSelectScreenState extends State<ModeSelectScreen> {
  final FlutterTts _tts = FlutterTts();
  bool _isDevMode = false;

  @override
  void initState() {
    super.initState();
    _initTts();
    _checkDevMode();
  }

  Future<void> _checkDevMode() async {
    try {
      const channel = MethodChannel('com.aiglasses/app_control');
      final result = await channel.invokeMethod<bool>('isDeveloperMode');
      debugPrint('[ModeSelect] isDeveloperMode = $result');
      if (mounted) setState(() => _isDevMode = result ?? false);
    } catch (e) {
      debugPrint('[ModeSelect] _checkDevMode 失敗: $e');
    }
  }

  Future<void> _initTts() async {
    await _tts.setLanguage('zh-TW');
    await _tts.setSpeechRate(0.45);
    await _tts.setVolume(1.0);
    // 稍微延遲再播，確保頁面已渲染
    await Future.delayed(const Duration(milliseconds: 600));
    if (!mounted) return;
    const text = '請選擇使用模式。上方大按鈕是視障者模式，下方是開發者模式。';
    final isTalkBackOn = WidgetsBinding.instance
        .platformDispatcher.accessibilityFeatures.accessibleNavigation;
    // 自動觸發語音：兩種模式都保留，但路由不同
    if (isTalkBackOn) {
      SemanticsService.announce(text, TextDirection.ltr);
    } else {
      await _tts.speak(text);
    }
  }

  @override
  void dispose() {
    _tts.stop();
    super.dispose();
  }

  Future<void> _selectMode(String mode) async {
    HapticFeedback.heavyImpact();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('user_mode', mode);
    if (!mounted) return;
    if (mode == 'blind') {
      // 按鈕語音已移入 Semantics 標籤，此處不重複播報
      await Future.delayed(const Duration(milliseconds: 300));
      if (mounted) Navigator.pushReplacementNamed(context, '/blind');
    } else {
      if (mounted) Navigator.pushReplacementNamed(context, '/home');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 16),
              const Text(
                '選擇使用模式',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                '此設定可在視障者模式設定頁切換',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 15, color: Colors.white54),
              ),
              const SizedBox(height: 24),

              // ── 視障者模式（大按鈕，佔主要空間）─────────────────────────
              Expanded(
                flex: 3,
                child: Semantics(
                  label: '視障者模式：全語音導引，無需看螢幕。點擊後進入視障者模式。',
                  button: true,
                  child: GestureDetector(
                    onTap: () => _selectMode('blind'),
                    child: Container(
                      decoration: BoxDecoration(
                        color: const Color(0xFF1565C0),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: Colors.blueAccent.withAlpha(128),
                          width: 2,
                        ),
                      ),
                      child: const Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.accessibility_new,
                            size: 80,
                            color: Colors.white,
                          ),
                          SizedBox(height: 20),
                          Text(
                            '視障者模式',
                            style: TextStyle(
                              fontSize: 38,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                          ),
                          SizedBox(height: 10),
                          Text(
                            '全語音導引，無需看螢幕',
                            style: TextStyle(
                              fontSize: 20,
                              color: Colors.white70,
                            ),
                          ),
                          SizedBox(height: 6),
                          Text(
                            '一鍵開始導航 • 語音緊急求救',
                            style: TextStyle(
                              fontSize: 16,
                              color: Colors.white54,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),

              // ── 開發者模式（僅手機開啟開發人員選項時顯示）──────────
              if (_isDevMode) ...[
                const SizedBox(height: 16),
                Expanded(
                  flex: 1,
                  child: Semantics(
                    label: '開發者模式：顯示詳細導航資訊與設定，點擊選擇',
                    button: true,
                    child: GestureDetector(
                      onTap: () => _selectMode('developer'),
                      child: Container(
                        decoration: BoxDecoration(
                          color: const Color(0xFF37474F),
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              Icons.developer_mode,
                              size: 36,
                              color: Colors.white70,
                            ),
                            SizedBox(width: 14),
                            Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  '開發者模式',
                                  style: TextStyle(
                                    fontSize: 24,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.white,
                                  ),
                                ),
                                Text(
                                  '顯示詳細資訊、AR 畫面與後台管理',
                                  style: TextStyle(
                                    fontSize: 14,
                                    color: Colors.white54,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],

              const SizedBox(height: 16),
            ],
          ),
        ),
      ),
    );
  }
}
