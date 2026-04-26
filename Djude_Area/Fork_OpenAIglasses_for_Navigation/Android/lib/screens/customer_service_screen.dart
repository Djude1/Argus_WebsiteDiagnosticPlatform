// lib/screens/customer_service_screen.dart
// 連線失敗時一般使用者看到的客服聯絡畫面
// 客服電話由 Website 後台 AppServerConfig.support_phone 設定

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';
import '../services/call_service.dart';

class CustomerServiceScreen extends StatefulWidget {
  const CustomerServiceScreen({super.key});

  @override
  State<CustomerServiceScreen> createState() => _CustomerServiceScreenState();
}

class _CustomerServiceScreenState extends State<CustomerServiceScreen> {
  final FlutterTts _tts = FlutterTts();

  @override
  void initState() {
    super.initState();
    _initTts();
  }

  Future<void> _initTts() async {
    await _tts.setLanguage('zh-TW');
    await _tts.setSpeechRate(0.5);
    await Future.delayed(const Duration(milliseconds: 500));
    if (!mounted) return;
    final phone = context.read<AppProvider>().supportPhone;
    final hasPhone = phone.isNotEmpty;
    final text = hasPhone
        ? '無法連線至伺服器。請聯絡客服，電話 $phone。點擊中央大按鈕直接撥打。'
        : '無法連線至伺服器。請聯絡客服人員，或稍後再試。';
    final isTalkBackOn = WidgetsBinding.instance
        .platformDispatcher.accessibilityFeatures.accessibleNavigation;
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

  Future<void> _callSupport(String phone) async {
    await _tts.speak('正在撥打客服電話');
    await CallService.call(phone);
  }

  Future<void> _retry() async {
    if (!mounted) return;
    Navigator.pushReplacementNamed(context, '/splash');
  }

  @override
  Widget build(BuildContext context) {
    final phone = context.watch<AppProvider>().supportPhone;
    final hasPhone = phone.isNotEmpty;

    return Scaffold(
      backgroundColor: const Color(0xFF0A0A0A),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // ── 標題區 ────────────────────────────────────────────────
              const Icon(
                Icons.wifi_off_rounded,
                size: 64,
                color: Colors.redAccent,
              ),
              const SizedBox(height: 20),
              const Text(
                '無法連線至伺服器',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                '請聯絡客服人員，或稍後重試',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 17, color: Colors.white60),
              ),

              const Spacer(),

              // ── 撥打按鈕（主要操作）────────────────────────────────────
              if (hasPhone) ...[
                Semantics(
                  label: '撥打客服電話 $phone，點擊直接撥出',
                  button: true,
                  child: GestureDetector(
                    onTap: () => _callSupport(phone),
                    child: Container(
                      height: 200,
                      decoration: BoxDecoration(
                        color: const Color(0xFF1B5E20),
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(
                          color: Colors.greenAccent.withAlpha(100),
                          width: 2,
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.green.withAlpha(50),
                            blurRadius: 20,
                            spreadRadius: 4,
                          ),
                        ],
                      ),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(
                            Icons.phone_rounded,
                            size: 72,
                            color: Colors.greenAccent,
                          ),
                          const SizedBox(height: 16),
                          const Text(
                            '撥打客服',
                            style: TextStyle(
                              fontSize: 28,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            phone,
                            style: const TextStyle(
                              fontSize: 22,
                              color: Colors.greenAccent,
                              letterSpacing: 2,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 20),
              ],

              // ── 客服未設定提示 ─────────────────────────────────────────
              if (!hasPhone)
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: Colors.white.withAlpha(10),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: const Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.support_agent_rounded,
                          size: 36, color: Colors.white38),
                      SizedBox(width: 14),
                      Expanded(
                        child: Text(
                          '客服電話尚未設定，\n請聯絡銷售人員獲取協助。',
                          style: TextStyle(fontSize: 18, color: Colors.white60),
                        ),
                      ),
                    ],
                  ),
                ),

              if (!hasPhone) const SizedBox(height: 20),

              // ── 重試按鈕 ──────────────────────────────────────────────
              Semantics(
                label: '重試連線，點擊重新嘗試連線至伺服器',
                button: true,
                child: SizedBox(
                  height: 64,
                  child: OutlinedButton.icon(
                    onPressed: _retry,
                    icon: const Icon(Icons.refresh_rounded,
                        size: 26, color: Colors.white54),
                    label: const Text(
                      '重試連線',
                      style: TextStyle(fontSize: 20, color: Colors.white70),
                    ),
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: Colors.white24),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                  ),
                ),
              ),

              const Spacer(),
            ],
          ),
        ),
      ),
    );
  }
}
