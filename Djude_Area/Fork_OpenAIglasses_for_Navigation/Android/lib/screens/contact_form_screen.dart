// lib/screens/contact_form_screen.dart
// 緊急聯絡人新增/編輯（視障友善版）
// • 大字體輸入欄位，標籤清楚
// • 進入時語音說明
// • 儲存/刪除為全寬大按鈕

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';

class ContactFormScreen extends StatefulWidget {
  final int slot;
  final Map<String, dynamic>? existing;

  const ContactFormScreen({
    super.key,
    required this.slot,
    this.existing,
  });

  @override
  State<ContactFormScreen> createState() => _ContactFormScreenState();
}

class _ContactFormScreenState extends State<ContactFormScreen> {
  late final TextEditingController _nameCtrl;
  late final TextEditingController _phoneCtrl;
  final FocusNode _nameFocus  = FocusNode();
  final FocusNode _phoneFocus = FocusNode();

  @override
  void initState() {
    super.initState();
    _nameCtrl  = TextEditingController(text: widget.existing?['name']  ?? '');
    _phoneCtrl = TextEditingController(text: widget.existing?['phone'] ?? '');

    WidgetsBinding.instance.addPostFrameCallback((_) {
      final isEdit = widget.existing != null;
      context.read<AppProvider>().speak(
        isEdit
            ? '編輯聯絡人 ${widget.existing!['name']}。'
              '修改姓名或電話後點擊下方儲存按鈕。'
            : '新增緊急連絡人。請輸入姓名，然後輸入電話號碼，最後點擊儲存。',
      );
    });
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _phoneCtrl.dispose();
    _nameFocus.dispose();
    _phoneFocus.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final name  = _nameCtrl.text.trim();
    final phone = _phoneCtrl.text.trim();

    if (name.isEmpty) {
      context.read<AppProvider>().speak('請輸入聯絡人姓名');
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('請輸入姓名'), behavior: SnackBarBehavior.floating),
      );
      _nameFocus.requestFocus();
      return;
    }
    if (phone.isEmpty) {
      context.read<AppProvider>().speak('請輸入電話號碼');
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('請輸入電話號碼'), behavior: SnackBarBehavior.floating),
      );
      _phoneFocus.requestFocus();
      return;
    }

    HapticFeedback.mediumImpact();
    final app = context.read<AppProvider>();
    if (widget.existing == null) {
      await app.addContact(name, phone);
      app.speak('已新增緊急連絡人 $name');
    } else {
      await app.updateContact(widget.existing!['id'] as int, name, phone);
      app.speak('已更新 $name 的資料');
    }
    if (mounted) Navigator.pop(context);
  }

  Future<void> _delete() async {
    final app  = context.read<AppProvider>();
    final name = widget.existing!['name'] as String;
    app.speak('確認是否刪除 $name');

    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1E1E1E),
        title: Text('刪除「$name」？',
            style: const TextStyle(fontSize: 22, color: Colors.white)),
        content: const Text('刪除後無法復原',
            style: TextStyle(fontSize: 16, color: Colors.white54)),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消', style: TextStyle(fontSize: 18)),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(
                backgroundColor: Colors.red.shade700),
            child: const Text('確認刪除', style: TextStyle(fontSize: 18)),
          ),
        ],
      ),
    );

    if (confirm == true && mounted) {
      await app.deleteContact(widget.existing!['id'] as int);
      app.speak('已刪除 $name');
      if (mounted) Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isEdit = widget.existing != null;

    return GestureDetector(
      onHorizontalDragEnd: (d) {
        if ((d.primaryVelocity ?? 0) > 300) Navigator.pop(context);
      },
      child: Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: Text(isEdit ? '編輯連絡人' : '新增連絡人'),
        backgroundColor: const Color(0xFF0D0D0D),
        automaticallyImplyLeading: false,
      ),
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [

            // ── 說明文字 ──────────────────────────────────────────────
            Container(
              color: const Color(0xFF0D0D0D),
              padding: const EdgeInsets.symmetric(
                  vertical: 10, horizontal: 20),
              child: Text(
                isEdit ? '修改完畢後點擊下方儲存按鈕' : '輸入姓名與電話號碼，再點擊儲存',
                style: const TextStyle(
                    fontSize: 15, color: Colors.white38),
              ),
            ),

            // ── 表單（可捲動）──────────────────────────────────────────
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 32, 24, 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [

                    // ── 姓名欄 ─────────────────────────────────────────
                    const Text('姓名',
                        style: TextStyle(
                            fontSize: 20, color: Colors.white60)),
                    const SizedBox(height: 10),
                    Semantics(
                      label: '姓名輸入欄位，例如媽媽、爸爸',
                      textField: true,
                      child: TextField(
                        controller:      _nameCtrl,
                        focusNode:       _nameFocus,
                        autofocus:       !isEdit,
                        textInputAction: TextInputAction.next,
                        onSubmitted:     (_) =>
                            _phoneFocus.requestFocus(),
                        style: const TextStyle(
                            fontSize: 28, color: Colors.white),
                        decoration: InputDecoration(
                          hintText:  '例如：媽媽',
                          hintStyle: const TextStyle(
                              color: Colors.white24, fontSize: 22),
                          filled:    true,
                          fillColor: const Color(0xFF1A1A1A),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: BorderSide.none,
                          ),
                          contentPadding: const EdgeInsets.symmetric(
                              horizontal: 20, vertical: 20),
                          prefixIcon: const Icon(
                              Icons.person,
                              color: Colors.white38,
                              size: 28),
                        ),
                      ),
                    ),
                    const SizedBox(height: 28),

                    // ── 電話欄 ─────────────────────────────────────────
                    const Text('電話號碼',
                        style: TextStyle(
                            fontSize: 20, color: Colors.white60)),
                    const SizedBox(height: 10),
                    Semantics(
                      label: '電話號碼輸入欄位',
                      textField: true,
                      child: TextField(
                        controller:      _phoneCtrl,
                        focusNode:       _phoneFocus,
                        keyboardType:    TextInputType.phone,
                        textInputAction: TextInputAction.done,
                        onSubmitted:     (_) => _save(),
                        style: const TextStyle(
                            fontSize: 28, color: Colors.white),
                        decoration: InputDecoration(
                          hintText:  '例如：0912345678',
                          hintStyle: const TextStyle(
                              color: Colors.white24, fontSize: 22),
                          filled:    true,
                          fillColor: const Color(0xFF1A1A1A),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: BorderSide.none,
                          ),
                          contentPadding: const EdgeInsets.symmetric(
                              horizontal: 20, vertical: 20),
                          prefixIcon: const Icon(
                              Icons.phone,
                              color: Colors.white38,
                              size: 28),
                        ),
                      ),
                    ),
                    const SizedBox(height: 40),

                    // ── 儲存按鈕（大）────────────────────────────────────
                    Semantics(
                      label:  isEdit ? '儲存修改' : '新增連絡人',
                      button: true,
                      child: GestureDetector(
                        onTap: _save,
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 24),
                          decoration: BoxDecoration(
                            color: const Color(0xFF1565C0),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(Icons.check, color: Colors.white, size: 32),
                              SizedBox(width: 12),
                              Text(
                                '儲存',
                                style: TextStyle(
                                  fontSize:   28,
                                  fontWeight: FontWeight.bold,
                                  color:      Colors.white,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),

                    // ── 刪除按鈕（僅編輯時顯示）─────────────────────────
                    if (isEdit) ...[
                      const SizedBox(height: 16),
                      Semantics(
                        label:  '刪除此連絡人',
                        button: true,
                        child: GestureDetector(
                          onTap: _delete,
                          child: Container(
                            padding:
                                const EdgeInsets.symmetric(vertical: 20),
                            decoration: BoxDecoration(
                              color:         Colors.transparent,
                              border:        Border.all(
                                  color: Colors.red.shade700, width: 2),
                              borderRadius: BorderRadius.circular(16),
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(Icons.delete,
                                    color: Colors.red.shade400, size: 28),
                                const SizedBox(width: 10),
                                Text(
                                  '刪除此連絡人',
                                  style: TextStyle(
                                    fontSize:   22,
                                    fontWeight: FontWeight.w600,
                                    color:      Colors.red.shade400,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ],
                  ],
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
