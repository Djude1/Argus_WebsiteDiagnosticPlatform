// lib/screens/emergency_countdown_screen.dart
// 撞擊偵測後的 20 秒倒數畫面
// 點擊取消按鈕可取消；倒數結束自動撥打第一位聯絡人

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';
import '../services/call_service.dart';

class EmergencyCountdownScreen extends StatefulWidget {
  final double magnitude;
  final void Function(String outcome) onOutcome;

  const EmergencyCountdownScreen({
    super.key,
    required this.magnitude,
    required this.onOutcome,
  });

  @override
  State<EmergencyCountdownScreen> createState() =>
      _EmergencyCountdownScreenState();
}

class _EmergencyCountdownScreenState extends State<EmergencyCountdownScreen> {
  static const int _totalSeconds = 20;
  int    _remaining = _totalSeconds;
  Timer? _timer;
  bool   _cancelled = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _start());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _start() {
    final app      = context.read<AppProvider>();
    final contacts = app.contacts;
    final name     = contacts.isNotEmpty
        ? (contacts.first['name'] as String? ?? '緊急聯絡人')
        : '緊急聯絡人';

    // 初始 TTS
    app.speak('偵測到劇烈撞擊，$_totalSeconds秒後撥打給$name，點擊取消按鈕可取消');

    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) { t.cancel(); return; }
      setState(() => _remaining--);

      if (_remaining <= 0) {
        t.cancel();
        HapticFeedback.heavyImpact();
        _dial();
        return;
      }

      // 最後 5 秒每秒重振動提醒
      if (_remaining <= 5) {
        HapticFeedback.heavyImpact();
      }

      // 每 5 秒報一次倒數
      if (_remaining % 5 == 0) {
        app.speak('還有$_remaining秒');
      }
    });
  }

  Future<void> _dial() async {
    if (_cancelled || !mounted) return;
    final contacts = context.read<AppProvider>().contacts;
    if (contacts.isEmpty) { Navigator.pop(context); return; }
    final phone = contacts.first['phone'] as String? ?? '';
    final name  = contacts.first['name']  as String? ?? '';
    context.read<AppProvider>().speak('正在撥打給$name');
    widget.onOutcome('auto_dialed');   // 記錄：自動撥出
    Navigator.pop(context);
    if (phone.isNotEmpty) {
      await CallService.call(phone);
    }
  }

  void _cancel() {
    if (_cancelled) return;
    _cancelled = true;
    _timer?.cancel();
    HapticFeedback.heavyImpact();
    widget.onOutcome('cancelled');     // 記錄：使用者取消
    context.read<AppProvider>().speak('已取消自動撥打');
    Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final contacts = context.watch<AppProvider>().contacts;
    final name     = contacts.isNotEmpty
        ? (contacts.first['name'] as String? ?? '緊急聯絡人')
        : '緊急聯絡人';

    // 倒數越少顏色越紅
    final urgency  = 1 - (_remaining / _totalSeconds);
    final bgColor  = Color.lerp(
      const Color(0xFF1A237E),   // 深藍
      const Color(0xFFB71C1C),   // 深紅
      urgency,
    )!;

    return Scaffold(
      backgroundColor: bgColor,
      body: SafeArea(
        child: Semantics(
          label: '緊急警示，$_remaining 秒後撥打給 $name，點擊取消按鈕可取消',
          liveRegion: true,
          child: GestureDetector(
            // 長按取消
            onLongPress: _cancel,
            behavior: HitTestBehavior.opaque,
            child: SizedBox.expand(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // ── 警示標題 ────────────────────────────────────────────
                  const Text(
                    '⚠ 偵測到劇烈撞擊',
                    style: TextStyle(
                        fontSize: 28,
                        fontWeight: FontWeight.bold,
                        color: Colors.white),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '$_remaining 秒後撥打給',
                    style: const TextStyle(fontSize: 22, color: Colors.white70),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    name,
                    style: const TextStyle(
                        fontSize: 36,
                        fontWeight: FontWeight.bold,
                        color: Colors.white),
                    textAlign: TextAlign.center,
                  ),

                  const SizedBox(height: 40),

                  // ── 倒數大數字（liveRegion 讓 TalkBack 自動播報更新）────
                  Semantics(
                    liveRegion: true,
                    label: '倒數 $_remaining 秒',
                    child: Text(
                      '$_remaining',
                      style: const TextStyle(
                          fontSize: 120,
                          fontWeight: FontWeight.bold,
                          color: Colors.white),
                    ),
                  ),

                  const SizedBox(height: 40),

                  // ── 取消按鈕 ────────────────────────────────────────────
                  Semantics(
                    label: '取消自動撥打',
                    button: true,
                    child: GestureDetector(
                      onTap: _cancel,
                      child: Container(
                        margin: const EdgeInsets.symmetric(horizontal: 40),
                        padding: const EdgeInsets.symmetric(vertical: 18),
                        decoration: BoxDecoration(
                          color: Colors.black38,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Center(
                          child: Text(
                            '點擊取消',
                            style: TextStyle(
                                fontSize: 28,
                                fontWeight: FontWeight.bold,
                                color: Colors.white),
                          ),
                        ),
                      ),
                    ),
                  ),

                  const SizedBox(height: 16),

                  // ── 返回首頁按鈕（取消倒數並返回）──────────────────────
                  Semantics(
                    label: '取消並返回首頁',
                    button: true,
                    child: GestureDetector(
                      onTap: () {
                        _cancel();
                        Navigator.of(context)
                            .popUntil((r) => r.isFirst);
                      },
                      child: Container(
                        margin: const EdgeInsets.symmetric(horizontal: 40),
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        decoration: BoxDecoration(
                          color: Colors.black26,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: Colors.white24),
                        ),
                        child: const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.home, color: Colors.white54, size: 22),
                            SizedBox(width: 8),
                            Text(
                              '返回首頁',
                              style: TextStyle(
                                  fontSize: 20,
                                  color: Colors.white54),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
