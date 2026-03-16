// lib/screens/admin/admin_screen.dart
// 後台首頁：系統狀態概覽、快速導航

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/auth_provider.dart';
import '../../providers/app_provider.dart';
import '../../core/theme.dart';

class AdminScreen extends StatefulWidget {
  const AdminScreen({super.key});

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen> {
  String _navState = '讀取中…';
  bool   _loading  = true;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() => _loading = true);
    try {
      final data = await context.read<AppProvider>().api.navState();
      if (mounted) {
        setState(() {
          _navState = data['state'] as String? ?? 'IDLE';
          _loading  = false;
        });
      }
    } catch (e) {
      if (mounted) setState(() { _navState = '無法連線'; _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final app  = context.watch<AppProvider>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('後台管理'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh),
          // 登出後台（回到 guest 模式）
          IconButton(
            icon:    const Icon(Icons.logout),
            tooltip: '登出後台',
            onPressed: () async {
              await context.read<AuthProvider>().logoutAdmin();
              if (context.mounted) {
                Navigator.pushNamedAndRemoveUntil(
                    context, '/home', (r) => false);
              }
            },
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ── 登入資訊 ─────────────────────────────────────────────────
            _InfoCard(
              icon:  Icons.person,
              title: '目前登入',
              value: '${auth.username}（${_roleLabel(auth.role)}）',
            ),
            const SizedBox(height: 12),

            // ── 伺服器狀態 ───────────────────────────────────────────────
            _InfoCard(
              icon:  Icons.cloud,
              title: '伺服器',
              value: '${app.host}:${app.port}',
              trailing: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: app.connected ? Colors.green : Colors.red,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  app.connected ? '已連線' : '未連線',
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                ),
              ),
            ),
            const SizedBox(height: 12),

            // ── 導航狀態 ─────────────────────────────────────────────────
            _InfoCard(
              icon:  Icons.navigation,
              title: '導航狀態',
              value: _loading ? '讀取中…' : _navState,
            ),
            const SizedBox(height: 24),

            // ── 管理選項 ─────────────────────────────────────────────────
            const Text('管理功能',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),

            if (auth.isAdmin) ...[
              _AdminTile(
                icon:  Icons.people,
                label: '使用者管理',
                sub:   '新增、停用、設定角色與密碼',
                onTap: () => Navigator.pushNamed(context, '/admin/users'),
              ),
              const SizedBox(height: 10),
            ],

            _AdminTile(
              icon:  Icons.contacts,
              label: '緊急連絡人',
              sub:   '管理語音撥打連絡人',
              onTap: () => Navigator.pushNamed(context, '/contacts'),
            ),
            const SizedBox(height: 10),

            _AdminTile(
              icon:  Icons.settings,
              label: '伺服器設定',
              sub:   '修改 IP 與 Port',
              onTap: () => Navigator.pushNamed(context, '/settings'),
            ),
          ],
        ),
      ),
    );
  }

  String _roleLabel(String role) {
    const map = {'admin': '管理員', 'operator': '操作員', 'user': '一般用戶'};
    return map[role] ?? role;
  }
}

class _InfoCard extends StatelessWidget {
  final IconData icon;
  final String   title;
  final String   value;
  final Widget?  trailing;

  const _InfoCard({
    required this.icon,
    required this.title,
    required this.value,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color:        AppTheme.surface,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(icon, color: Colors.white70, size: 28),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(color: Colors.white54, fontSize: 13)),
                Text(value,
                    style: const TextStyle(fontSize: 16,
                        fontWeight: FontWeight.bold)),
              ],
            ),
          ),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

class _AdminTile extends StatelessWidget {
  final IconData icon;
  final String   label;
  final String   sub;
  final VoidCallback onTap;

  const _AdminTile({
    required this.icon,
    required this.label,
    required this.sub,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppTheme.surface,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Icon(icon, size: 32, color: Colors.white70),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label,
                        style: const TextStyle(fontSize: 18,
                            fontWeight: FontWeight.bold)),
                    Text(sub,
                        style: const TextStyle(color: Colors.white54,
                            fontSize: 14)),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: Colors.white38),
            ],
          ),
        ),
      ),
    );
  }
}
