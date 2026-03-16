// lib/screens/admin_login_screen.dart
// 後台管理員登入（獨立畫面，從主畫面隱藏入口進入）

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import '../providers/app_provider.dart';
import '../core/theme.dart';

class AdminLoginScreen extends StatefulWidget {
  const AdminLoginScreen({super.key});

  @override
  State<AdminLoginScreen> createState() => _AdminLoginScreenState();
}

class _AdminLoginScreenState extends State<AdminLoginScreen> {
  final _userCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  bool    _loading = false;
  String? _error;

  Future<void> _login() async {
    setState(() { _loading = true; _error = null; });

    final auth = context.read<AuthProvider>();
    final app  = context.read<AppProvider>();

    final err = await auth.loginAdmin(
      _userCtrl.text.trim(),
      _passCtrl.text,
      app.api,
    );

    if (!mounted) return;
    setState(() => _loading = false);

    if (err != null) {
      setState(() => _error = err);
    } else {
      Navigator.pushReplacementNamed(context, '/admin');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('後台管理員登入'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Icon(Icons.admin_panel_settings,
                  size: 64, color: Colors.white54),
              const SizedBox(height: 16),
              const Text(
                '管理後台',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 40),

              TextField(
                controller:      _userCtrl,
                autofocus:       true,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(
                  labelText:  '帳號',
                  prefixIcon: Icon(Icons.person),
                ),
              ),
              const SizedBox(height: 16),

              TextField(
                controller:      _passCtrl,
                obscureText:     true,
                textInputAction: TextInputAction.done,
                onSubmitted:     (_) => _login(),
                decoration: const InputDecoration(
                  labelText:  '密碼',
                  prefixIcon: Icon(Icons.lock),
                ),
              ),
              const SizedBox(height: 8),

              if (_error != null)
                Text(_error!,
                    style: const TextStyle(color: Colors.red, fontSize: 15)),

              const SizedBox(height: 24),

              ElevatedButton(
                onPressed: _loading ? null : _login,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.colorAdmin,
                  minimumSize: const Size(double.infinity, 64),
                ),
                child: _loading
                    ? const CircularProgressIndicator(color: Colors.white)
                    : const Text('登入後台', style: TextStyle(fontSize: 20)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
