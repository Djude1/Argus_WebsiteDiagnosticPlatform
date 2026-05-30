// lib/screens/emergency_select_screen.dart
// 緊急求救選人畫面：固定兩大色塊，視障者選擇後立即撥打
// 沒有設定聯絡人的欄位顯示「尚未設定」並提示到設定頁面新增

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';
import '../services/call_service.dart';

class EmergencySelectScreen extends StatefulWidget {
  const EmergencySelectScreen({super.key});

  @override
  State<EmergencySelectScreen> createState() => _EmergencySelectScreenState();
}

class _EmergencySelectScreenState extends State<EmergencySelectScreen> {
  // 固定兩欄位的顏色
  static const _colors = [Color(0xFF0D47A1), Color(0xFFE65100)];
  static const _labels = ['主要聯絡人', '次要聯絡人'];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final app = context.read<AppProvider>();
      final contacts = app.contacts;
      if (contacts.isEmpty) {
        app.speak('尚未設定緊急連絡人，請到設定頁面新增。向右滑動返回。');
      } else {
        final names = contacts.map((c) => c['name'] as String).join('或');
        app.speak('請選擇求救對象：$names。向右滑動取消。');
      }
    });
  }

  Future<void> _call(Map<String, dynamic> contact) async {
    HapticFeedback.heavyImpact();
    final phone = contact['phone'] as String? ?? '';
    if (phone.isEmpty) return;
    if (mounted) Navigator.pop(context);
    await CallService.call(phone);
  }

  @override
  Widget build(BuildContext context) {
    final contacts = context.watch<AppProvider>().contacts;

    return GestureDetector(
      onHorizontalDragEnd: (details) {
        if ((details.primaryVelocity ?? 0) > 300) {
          context.read<AppProvider>().speak('取消，返回上一頁');
          Navigator.pop(context);
        }
      },
      child: Scaffold(
        backgroundColor: Colors.black,
        body: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // ── 頂部標題 ──────────────────────────────────────────────
              Container(
                color: const Color(0xFF1A1A1A),
                padding: const EdgeInsets.symmetric(
                    vertical: 10, horizontal: 20),
                child: const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '緊急求救',
                      style: TextStyle(
                          fontSize: 26,
                          fontWeight: FontWeight.bold,
                          color: Colors.white),
                    ),
                    SizedBox(height: 4),
                    Text(
                      '向右滑動取消返回',
                      style: TextStyle(fontSize: 13, color: Colors.white38),
                    ),
                  ],
                ),
              ),

              // ── 固定兩大色塊 ──────────────────────────────────────────
              for (int i = 0; i < 2; i++) ...[
                Expanded(
                  child: _buildSlot(i, contacts),
                ),
                if (i == 0) const SizedBox(height: 4),
              ],

              // 底部間距
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSlot(int index, List<Map<String, dynamic>> contacts) {
    final hasContact = index < contacts.length;
    final contact = hasContact ? contacts[index] : null;
    final name = contact?['name'] as String? ?? '';
    final phone = contact?['phone'] as String? ?? '';

    if (!hasContact) {
      // 沒有設定：顯示灰色提示
      return Semantics(
        label: '${_labels[index]}尚未設定，請到設定頁面新增',
        child: Container(
          color: const Color(0xFF2A2A2A),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.person_add_alt_1,
                  size: 48, color: Colors.white24),
              const SizedBox(height: 12),
              Text(
                _labels[index],
                style: const TextStyle(fontSize: 18, color: Colors.white38),
              ),
              const SizedBox(height: 6),
              const Text(
                '尚未設定',
                style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                    color: Colors.white24),
              ),
            ],
          ),
        ),
      );
    }

    // 有聯絡人：可撥打
    return Semantics(
      label: phone.isEmpty
          ? '${_labels[index]}$name，電話未設定，無法撥打'
          : '點擊撥打電話給$name，號碼$phone',
      button: true,
      child: GestureDetector(
        onTap: () => _call(contact!),
        child: Container(
          color: _colors[index],
          padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 28),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                _labels[index],
                style: const TextStyle(fontSize: 18, color: Colors.white70),
              ),
              const SizedBox(height: 8),
              Text(
                name,
                style: const TextStyle(
                    fontSize: 44,
                    fontWeight: FontWeight.bold,
                    color: Colors.white),
              ),
              const SizedBox(height: 6),
              Text(
                phone,
                style: const TextStyle(fontSize: 24, color: Colors.white70),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
