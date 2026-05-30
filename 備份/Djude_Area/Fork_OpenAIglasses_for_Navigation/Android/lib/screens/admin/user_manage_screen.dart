// lib/screens/admin/user_manage_screen.dart
// 使用者管理畫面（Admin 限定）：新增、停用/啟用、修改角色、修改密碼、刪除

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/auth_provider.dart';
import '../../providers/app_provider.dart';
import '../../core/theme.dart';

class UserManageScreen extends StatefulWidget {
  const UserManageScreen({super.key});

  @override
  State<UserManageScreen> createState() => _UserManageScreenState();
}

class _UserManageScreenState extends State<UserManageScreen> {
  List<dynamic> _users   = [];
  bool          _loading = true;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() => _loading = true);
    try {
      final list = await context.read<AppProvider>().api.listUsers();
      if (mounted) setState(() { _users = list; _loading = false; });
    } catch (e) {
      if (mounted) setState(() => _loading = false);
    }
  }

  // ── 新增使用者對話框 ─────────────────────────────────────────────────────
  Future<void> _showAddDialog() async {
    final userCtrl = TextEditingController();
    final passCtrl = TextEditingController();
    String role    = 'user';

    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setD) => AlertDialog(
          backgroundColor: AppTheme.surface,
          title: const Text('新增使用者'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: userCtrl,
                autofocus:  true,
                decoration: const InputDecoration(
                    labelText: '帳號', prefixIcon: Icon(Icons.person)),
              ),
              const SizedBox(height: 10),
              TextField(
                controller:  passCtrl,
                obscureText: true,
                decoration: const InputDecoration(
                    labelText: '密碼', prefixIcon: Icon(Icons.lock)),
              ),
              const SizedBox(height: 10),
              DropdownButtonFormField<String>(
                value: role,
                dropdownColor: AppTheme.surface,
                decoration: const InputDecoration(labelText: '角色'),
                items: const [
                  DropdownMenuItem(value: 'user',     child: Text('一般用戶')),
                  DropdownMenuItem(value: 'operator', child: Text('操作員')),
                  DropdownMenuItem(value: 'admin',    child: Text('管理員')),
                ],
                onChanged: (v) => setD(() => role = v ?? 'user'),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false),
                child: const Text('取消')),
            ElevatedButton(onPressed: () => Navigator.pop(ctx, true),
                child: const Text('新增')),
          ],
        ),
      ),
    );
    if (saved != true || !mounted) return;
    try {
      await context.read<AppProvider>().api.createUser(
          userCtrl.text.trim(), passCtrl.text, role);
      await _refresh();
    } catch (e) {
      if (mounted) _showError('新增失敗：$e');
    }
  }

  // ── 修改密碼 ─────────────────────────────────────────────────────────────
  Future<void> _showChangePasswordDialog(int userId, String username) async {
    final passCtrl = TextEditingController();
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppTheme.surface,
        title: Text('修改 $username 的密碼'),
        content: TextField(
          controller:  passCtrl,
          obscureText: true,
          autofocus:   true,
          decoration: const InputDecoration(labelText: '新密碼'),
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
    try {
      await context.read<AppProvider>().api.updateUser(userId,
          password: passCtrl.text);
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('密碼已更新')));
    } catch (e) {
      if (mounted) _showError('更新失敗：$e');
    }
  }

  // ── 刪除確認 ─────────────────────────────────────────────────────────────
  Future<void> _deleteUser(int id, String username) async {
    final selfId = context.read<AuthProvider>().userId;
    if (id == selfId) { _showError('不能刪除自己'); return; }

    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('刪除使用者「$username」？'),
        content: const Text('此操作無法復原，連絡人資料也會一併刪除。'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消')),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(backgroundColor: AppTheme.colorStop),
            child: const Text('刪除'),
          ),
        ],
      ),
    );
    if (confirm != true || !mounted) return;
    try {
      await context.read<AppProvider>().api.deleteUser(id);
      await _refresh();
    } catch (e) {
      if (mounted) _showError('刪除失敗：$e');
    }
  }

  void _showError(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(msg), backgroundColor: AppTheme.colorStop));
  }

  String _roleLabel(String role) {
    const map = {'admin': '管理員', 'operator': '操作員', 'user': '一般用戶'};
    return map[role] ?? role;
  }

  Color _roleColor(String role) {
    if (role == 'admin')    return Colors.orangeAccent;
    if (role == 'operator') return Colors.blueAccent;
    return Colors.white54;
  }

  @override
  Widget build(BuildContext context) {
    final selfId = context.watch<AuthProvider>().userId;

    return Scaffold(
      appBar: AppBar(
        title: const Text('使用者管理'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: _users.length,
              itemBuilder: (_, i) {
                final u        = _users[i] as Map<String, dynamic>;
                final uid      = u['id']       as int;
                final username = u['username'] as String;
                final role     = u['role']     as String;
                final enabled  = (u['enabled'] as int) == 1;
                final isSelf   = uid == selfId;

                return Card(
                  color:  AppTheme.surface,
                  margin: const EdgeInsets.only(bottom: 10),
                  child: ListTile(
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 8),
                    leading: CircleAvatar(
                      backgroundColor: _roleColor(role).withValues(alpha: 0.2),
                      child: Text(username[0].toUpperCase(),
                          style: TextStyle(color: _roleColor(role),
                              fontWeight: FontWeight.bold)),
                    ),
                    title: Row(
                      children: [
                        Text(username,
                            style: const TextStyle(fontSize: 16,
                                fontWeight: FontWeight.bold)),
                        if (isSelf) ...[
                          const SizedBox(width: 6),
                          const Text('（自己）',
                              style: TextStyle(color: Colors.white38,
                                  fontSize: 12)),
                        ],
                      ],
                    ),
                    subtitle: Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: _roleColor(role).withValues(alpha: 0.15),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(_roleLabel(role),
                              style: TextStyle(color: _roleColor(role),
                                  fontSize: 12)),
                        ),
                        const SizedBox(width: 8),
                        Icon(
                          enabled ? Icons.check_circle : Icons.cancel,
                          size: 14,
                          color: enabled ? Colors.green : Colors.red,
                        ),
                        const SizedBox(width: 4),
                        Text(enabled ? '啟用' : '停用',
                            style: TextStyle(
                                color: enabled ? Colors.green : Colors.red,
                                fontSize: 12)),
                      ],
                    ),
                    trailing: isSelf
                        ? null
                        : PopupMenuButton<String>(
                            color: AppTheme.surface,
                            onSelected: (action) async {
                              switch (action) {
                                case 'toggle':
                                  await context.read<AppProvider>().api
                                      .updateUser(uid, enabled: !enabled);
                                  await _refresh();
                                case 'password':
                                  await _showChangePasswordDialog(uid, username);
                                case 'role_user':
                                  await context.read<AppProvider>().api
                                      .updateUser(uid, role: 'user');
                                  await _refresh();
                                case 'role_operator':
                                  await context.read<AppProvider>().api
                                      .updateUser(uid, role: 'operator');
                                  await _refresh();
                                case 'role_admin':
                                  await context.read<AppProvider>().api
                                      .updateUser(uid, role: 'admin');
                                  await _refresh();
                                case 'delete':
                                  await _deleteUser(uid, username);
                              }
                            },
                            itemBuilder: (_) => [
                              PopupMenuItem(
                                value: 'toggle',
                                child: Row(children: [
                                  Icon(enabled
                                      ? Icons.cancel
                                      : Icons.check_circle,
                                      size: 18),
                                  const SizedBox(width: 8),
                                  Text(enabled ? '停用帳號' : '啟用帳號'),
                                ]),
                              ),
                              const PopupMenuItem(
                                value: 'password',
                                child: Row(children: [
                                  Icon(Icons.lock_reset, size: 18),
                                  SizedBox(width: 8),
                                  Text('修改密碼'),
                                ]),
                              ),
                              const PopupMenuDivider(),
                              const PopupMenuItem(
                                value: 'role_user',
                                child: Text('設為 一般用戶'),
                              ),
                              const PopupMenuItem(
                                value: 'role_operator',
                                child: Text('設為 操作員'),
                              ),
                              const PopupMenuItem(
                                value: 'role_admin',
                                child: Text('設為 管理員'),
                              ),
                              const PopupMenuDivider(),
                              const PopupMenuItem(
                                value: 'delete',
                                child: Row(children: [
                                  Icon(Icons.delete, color: Colors.red,
                                      size: 18),
                                  SizedBox(width: 8),
                                  Text('刪除',
                                      style: TextStyle(color: Colors.red)),
                                ]),
                              ),
                            ],
                          ),
                  ),
                );
              },
            ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _showAddDialog,
        icon:  const Icon(Icons.person_add),
        label: const Text('新增使用者'),
        backgroundColor: AppTheme.primary,
      ),
    );
  }
}
