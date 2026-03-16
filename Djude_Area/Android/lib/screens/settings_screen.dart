// lib/screens/settings_screen.dart
// 伺服器連線設定：IP、Port

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';
import '../core/constants.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late TextEditingController _hostCtrl;
  late TextEditingController _portCtrl;
  late bool _secure;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final app = context.read<AppProvider>();
    _hostCtrl = TextEditingController(text: app.host);
    _portCtrl = TextEditingController(text: app.port.toString());
    _secure   = app.secure;
  }

  Future<void> _save() async {
    final host = _hostCtrl.text.trim();
    final port = int.tryParse(_portCtrl.text.trim());
    if (host.isEmpty || port == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('請輸入有效的 IP 與 Port')),
      );
      return;
    }
    setState(() => _saving = true);
    final app = context.read<AppProvider>();
    await app.updateServerSettings(host, port, secure: _secure);

    // 嘗試連線，確認伺服器是否可達（用 /api/health，不需 token）
    bool ok = false;
    try {
      ok = await app.api.healthCheck();
    } catch (_) {}

    setState(() => _saving = false);
    if (!mounted) return;

    if (ok) {
      // 連線成功 → 啟動服務並進主畫面
      await app.startAllServices();
      Navigator.pushReplacementNamed(context, '/home');
    } else {
      // 連不到 → 停留在設定頁顯示錯誤
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('無法連線到 $host:$port，請確認 IP 與伺服器狀態')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('伺服器設定')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('伺服器 IP 位址',
                style: TextStyle(fontSize: 16, color: Colors.white70)),
            const SizedBox(height: 8),
            TextField(
              controller:   _hostCtrl,
              keyboardType: TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(
                hintText: '例如：192.168.1.100',
                prefixIcon: Icon(Icons.computer),
              ),
            ),
            const SizedBox(height: 20),
            const Text('伺服器 Port',
                style: TextStyle(fontSize: 16, color: Colors.white70)),
            const SizedBox(height: 8),
            TextField(
              controller:   _portCtrl,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                hintText: '預設 8081',
                prefixIcon: Icon(Icons.settings_ethernet),
              ),
            ),
            const SizedBox(height: 12),
            Text(
              '目前連線：${context.watch<AppProvider>().host}:${context.watch<AppProvider>().port}',
              style: const TextStyle(color: Colors.white54, fontSize: 14),
            ),
            const SizedBox(height: 8),
            // 模擬器快速填入提示（10.0.2.2 = 模擬器內存取 host 電腦的特殊 IP）
            TextButton.icon(
              onPressed: () {
                _hostCtrl.text = '10.0.2.2';
                _portCtrl.text = '8081';
                setState(() => _secure = false);
              },
              icon: const Icon(Icons.phone_android, size: 16),
              label: const Text('使用模擬器預設（10.0.2.2）'),
              style: TextButton.styleFrom(foregroundColor: Colors.white38),
            ),
            const SizedBox(height: 4),
            // TLS 開關（公網連線請開啟）
            StatefulBuilder(
              builder: (_, setState2) => SwitchListTile(
                value: _secure,
                onChanged: (v) {
                  setState(() => _secure = v);
                  if (v && _portCtrl.text == '8081') _portCtrl.text = '443';
                  if (!v && _portCtrl.text == '443') _portCtrl.text = '8081';
                },
                title: const Text('啟用 TLS（公網 wss:// / https://）',
                    style: TextStyle(fontSize: 14, color: Colors.white70)),
                subtitle: Text(
                  _secure ? '連線加密，適合公網使用' : '明文連線，適合區網使用',
                  style: const TextStyle(fontSize: 12, color: Colors.white38),
                ),
                activeColor: Colors.blueAccent,
                contentPadding: EdgeInsets.zero,
              ),
            ),
            const SizedBox(height: 8),
            ElevatedButton(
              onPressed: _saving ? null : _save,
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF1565C0),
                minimumSize: const Size(double.infinity, 64),
              ),
              child: _saving
                  ? const CircularProgressIndicator(color: Colors.white)
                  : const Text('儲存', style: TextStyle(fontSize: 20)),
            ),
          ],
        ),
      ),
    );
  }
}
