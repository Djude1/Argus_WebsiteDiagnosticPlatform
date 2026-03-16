// lib/screens/contacts_screen.dart
// 緊急連絡人管理（本機儲存，不需登入）

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';
import '../core/theme.dart';

class ContactsScreen extends StatefulWidget {
  const ContactsScreen({super.key});

  @override
  State<ContactsScreen> createState() => _ContactsScreenState();
}

class _ContactsScreenState extends State<ContactsScreen> {
  @override
  void initState() {
    super.initState();
    context.read<AppProvider>().loadContacts();
  }

  Future<void> _showDialog({Map<String, dynamic>? existing}) async {
    final nameCtrl  = TextEditingController(text: existing?['name']  ?? '');
    final phoneCtrl = TextEditingController(text: existing?['phone'] ?? '');

    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppTheme.surface,
        title: Text(existing == null ? '新增連絡人' : '編輯連絡人',
            style: const TextStyle(fontSize: 20)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameCtrl,
              autofocus:  true,
              decoration: const InputDecoration(
                labelText:  '姓名（語音呼叫時說「打給＋姓名」）',
                hintText:   '例如：媽媽',
                prefixIcon: Icon(Icons.person),
              ),
              style: const TextStyle(fontSize: 18),
            ),
            const SizedBox(height: 12),
            TextField(
              controller:   phoneCtrl,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(
                labelText:  '電話號碼',
                hintText:   '例如：0912345678',
                prefixIcon: Icon(Icons.phone),
              ),
              style: const TextStyle(fontSize: 18),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消')),
          ElevatedButton(onPressed: () => Navigator.pop(ctx, true),
              child: const Text('儲存')),
        ],
      ),
    );
    if (saved != true || !mounted) return;

    final name  = nameCtrl.text.trim();
    final phone = phoneCtrl.text.trim();
    if (name.isEmpty || phone.isEmpty) return;

    final app = context.read<AppProvider>();
    if (existing == null) {
      await app.addContact(name, phone);
    } else {
      await app.updateContact(existing['id'] as int, name, phone);
    }
  }

  Future<void> _delete(int id, String name) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('刪除「$name」？'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消')),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.colorStop),
            child: const Text('刪除'),
          ),
        ],
      ),
    );
    if (confirm == true && mounted) {
      await context.read<AppProvider>().deleteContact(id);
    }
  }

  @override
  Widget build(BuildContext context) {
    final contacts = context.watch<AppProvider>().contacts;

    return Scaffold(
      appBar: AppBar(title: const Text('緊急連絡人')),
      body: contacts.isEmpty
          ? Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.contacts,
                      size: 64, color: Colors.white38),
                  const SizedBox(height: 12),
                  const Text('尚無連絡人',
                      style: TextStyle(
                          color: Colors.white54, fontSize: 18)),
                  const SizedBox(height: 8),
                  const Text(
                    '新增後說「打給媽媽」可自動撥號\n（姓名需完全相符）',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                        color: Colors.white38, fontSize: 14),
                  ),
                ],
              ),
            )
          : ListView.builder(
              padding:     const EdgeInsets.all(12),
              itemCount:   contacts.length,
              itemBuilder: (_, i) {
                final c = contacts[i];
                return Card(
                  color:  AppTheme.surface,
                  margin: const EdgeInsets.only(bottom: 10),
                  child: ListTile(
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 8),
                    leading: Semantics(
                      label:  '撥打給${c['name']}',
                      button: true,
                      child: IconButton(
                        icon: const Icon(Icons.phone,
                            color: Colors.greenAccent, size: 32),
                        onPressed: () => context
                            .read<AppProvider>()
                            .callContact(
                              c['name']  as String,
                              c['phone'] as String,
                            ),
                      ),
                    ),
                    title: Text(c['name'] as String,
                        style: const TextStyle(
                            fontSize:   20,
                            fontWeight: FontWeight.bold)),
                    subtitle: Text(c['phone'] as String,
                        style: const TextStyle(
                            fontSize: 16, color: Colors.white70)),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        IconButton(
                          icon: const Icon(Icons.edit,
                              color: Colors.white54),
                          onPressed: () => _showDialog(existing: c),
                        ),
                        IconButton(
                          icon: const Icon(Icons.delete,
                              color: Colors.redAccent),
                          onPressed: () => _delete(
                              c['id'] as int, c['name'] as String),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
      floatingActionButton: Semantics(
        label:  '新增緊急連絡人',
        button: true,
        child: FloatingActionButton.extended(
          onPressed:       () => _showDialog(),
          icon:            const Icon(Icons.add),
          label:           const Text('新增連絡人',
              style: TextStyle(fontSize: 16)),
          backgroundColor: AppTheme.primary,
        ),
      ),
    );
  }
}
