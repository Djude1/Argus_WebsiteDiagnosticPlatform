// lib/screens/login_screen.dart
// 登入畫面：大字體輸入、視障友善

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import '../providers/app_provider.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _userCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  bool  _loading  = false;
  String? _error;

  Future<void> _login() async {
    setState(() { _loading = true; _error = null; });
    final appProvider  = context.read<AppProvider>();
    final authProvider = context.read<AuthProvider>();

    final err = await authProvider.login(
      _userCtrl.text.trim(),
      _passCtrl.text,
      appProvider.api,
    );

    if (!mounted) return;
    setState(() { _loading = false; });

    if (err != null) {
      setState(() { _error = err; });
    } else {
      await appProvider.startAllServices(token: '');
      appProvider.startPollingNavState();
      if (mounted) Navigator.pushReplacementNamed(context, '/home');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Icon(Icons.visibility, size: 64, color: Colors.white),
              const SizedBox(height: 16),
              const Text(
                'AI 智慧眼鏡',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 40),

              // 帳號輸入
              Semantics(
                label: '輸入帳號',
                child: TextField(
                  controller:   _userCtrl,
                  autofocus:    true,
                  keyboardType: TextInputType.text,
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(
                    labelText: '帳號',
                    prefixIcon: Icon(Icons.person),
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // 密碼輸入
              Semantics(
                label: '輸入密碼',
                child: TextField(
                  controller:  _passCtrl,
                  obscureText: true,
                  textInputAction: TextInputAction.done,
                  onSubmitted:  (_) => _login(),
                  decoration: const InputDecoration(
                    labelText: '密碼',
                    prefixIcon: Icon(Icons.lock),
                  ),
                ),
              ),
              const SizedBox(height: 8),

              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text(_error!,
                      style: const TextStyle(color: Colors.red, fontSize: 16)),
                ),

              const SizedBox(height: 16),

              // 登入按鈕
              Semantics(
                label: '登入',
                button: true,
                child: ElevatedButton(
                  onPressed: _loading ? null : _login,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF1565C0),
                    minimumSize: const Size(double.infinity, 72),
                  ),
                  child: _loading
                      ? const CircularProgressIndicator(color: Colors.white)
                      : const Text('登入', style: TextStyle(fontSize: 22)),
                ),
              ),
              const SizedBox(height: 12),

              // 前往伺服器設定
              TextButton(
                onPressed: () => Navigator.pushNamed(context, '/settings'),
                child: const Text('設定伺服器連線',
                    style: TextStyle(fontSize: 16, color: Colors.white70)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
