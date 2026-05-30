// lib/screens/contacts_screen.dart
// 緊急連絡人設定（視障友善版）
// • 固定兩大色塊：主要聯絡人、次要聯絡人
// • 點擊 → 進入編輯介面（設定頁只負責設定，不撥打）
// • 最多 2 位，沒設定的顯示「點擊新增」
// • 向右滑動返回

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';
import 'contact_form_screen.dart';

class ContactsScreen extends StatefulWidget {
  const ContactsScreen({super.key});

  @override
  State<ContactsScreen> createState() => _ContactsScreenState();
}

class _ContactsScreenState extends State<ContactsScreen> {
  static const _colors = [Color(0xFF0D47A1), Color(0xFFE65100)];
  static const _labels = ['主要聯絡人', '次要聯絡人'];

  @override
  void initState() {
    super.initState();
    context.read<AppProvider>().loadContacts();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final app = context.read<AppProvider>();
      final n = app.contacts.length;
      if (n == 0) {
        app.speak('緊急連絡人設定。目前沒有聯絡人，點擊色塊可新增。最多設定兩位。向右滑動返回。');
      } else {
        final names = app.contacts.map((c) => c['name']).join('和');
        app.speak('緊急連絡人設定。已設定$names。點擊可修改。向右滑動返回。');
      }
    });
  }

  Future<void> _editSlot(int slot) async {
    HapticFeedback.heavyImpact();
    final app = context.read<AppProvider>();
    final contacts = app.contacts;
    final existing = slot < contacts.length ? contacts[slot] : null;

    if (existing != null) {
      app.speak('修改${_labels[slot]}${existing['name']}');
    } else {
      app.speak('新增${_labels[slot]}');
    }

    if (!mounted) return;
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ContactFormScreen(
          slot: slot,
          existing: existing,
        ),
      ),
    );
    // 返回後重新載入
    if (mounted) {
      context.read<AppProvider>().loadContacts();
    }
  }

  @override
  Widget build(BuildContext context) {
    final contacts = context.watch<AppProvider>().contacts;

    return GestureDetector(
      onHorizontalDragEnd: (d) {
        if ((d.primaryVelocity ?? 0) > 300) Navigator.pop(context);
      },
      child: Scaffold(
        backgroundColor: Colors.black,
        body: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // ── 頂部標題 ──────────────────────────────────────────────
              Container(
                color: const Color(0xFF0D0D0D),
                padding: const EdgeInsets.symmetric(
                    vertical: 10, horizontal: 20),
                child: const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '緊急連絡人設定',
                      style: TextStyle(
                          fontSize: 24,
                          fontWeight: FontWeight.bold,
                          color: Colors.white),
                    ),
                    SizedBox(height: 4),
                    Text(
                      '點擊可修改，最多兩位。向右滑動返回。',
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

    return Semantics(
      label: hasContact
          ? '${_labels[index]}，$name，$phone。點擊修改。'
          : '${_labels[index]}，尚未設定。點擊新增。',
      button: true,
      child: GestureDetector(
        onTap: () => _editSlot(index),
        child: Container(
          color: hasContact ? _colors[index] : const Color(0xFF2A2A2A),
          padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 28),
          child: Row(
            children: [
              // 左側圖示
              Icon(
                hasContact ? Icons.edit : Icons.person_add_alt_1,
                size: 40,
                color: hasContact ? Colors.white70 : Colors.white24,
              ),
              const SizedBox(width: 20),
              // 右側資訊
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _labels[index],
                      style: TextStyle(
                        fontSize: 16,
                        color: hasContact ? Colors.white70 : Colors.white38,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      hasContact ? name : '點擊新增',
                      style: TextStyle(
                        fontSize: 36,
                        fontWeight: FontWeight.bold,
                        color: hasContact ? Colors.white : Colors.white30,
                      ),
                    ),
                    if (hasContact) ...[
                      const SizedBox(height: 4),
                      Text(
                        phone,
                        style: const TextStyle(
                            fontSize: 20, color: Colors.white60),
                      ),
                    ],
                    if (!hasContact)
                      const Text(
                        '尚未設定',
                        style: TextStyle(fontSize: 14, color: Colors.white24),
                      ),
                  ],
                ),
              ),
              // 右側箭頭
              Icon(
                Icons.chevron_right,
                size: 32,
                color: hasContact ? Colors.white38 : Colors.white12,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
