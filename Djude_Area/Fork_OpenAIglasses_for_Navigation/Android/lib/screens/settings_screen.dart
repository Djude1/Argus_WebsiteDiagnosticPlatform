// lib/screens/settings_screen.dart
// 伺服器連線設定：URL 或 IP + Port

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
  late TextEditingController _urlCtrl;
  late TextEditingController _hostCtrl;
  late TextEditingController _portCtrl;
  late bool _secure;
  bool _useUrlMode = true;  // 預設使用 URL 模式
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final app = context.read<AppProvider>();
    _urlCtrl  = TextEditingController(text: app.baseUrl);
    _hostCtrl = TextEditingController(text: app.host);
    _portCtrl = TextEditingController(text: app.port.toString());
    _secure   = app.secure;
    // 如果有 baseUrl 且是完整 URL，預設使用 URL 模式
    _useUrlMode = app.baseUrl.isNotEmpty && AppConstants.isFullUrl(app.baseUrl);
  }

  Future<void> _save() async {
    String baseUrl = '';
    String host;
    int port;

    if (_useUrlMode) {
      baseUrl = _urlCtrl.text.trim();
      if (!AppConstants.isFullUrl(baseUrl)) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('URL 必須以 http:// 或 https:// 開頭')),
        );
        return;
      }
      // 從 URL 解析 host 和 port
      final parsed = AppConstants.parseUrl(baseUrl);
      host = parsed.host;
      port = parsed.port;
      _secure = parsed.secure;
    } else {
      host = _hostCtrl.text.trim();
      port = int.tryParse(_portCtrl.text.trim()) ?? AppConstants.defaultPort;
      if (host.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('請輸入有效的 IP 與 Port')),
        );
        return;
      }
    }

    setState(() => _saving = true);
    final app = context.read<AppProvider>();
    await app.updateServerSettings(host, port, secure: _secure, baseUrl: baseUrl);

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
      final displayUrl = _useUrlMode ? baseUrl : '$host:$port';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('無法連線到 $displayUrl，請確認設定與伺服器狀態')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('伺服器設定')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ── 模式切換 ────────────────────────────────────────────────────
            SegmentedButton<bool>(
              segments: const [
                ButtonSegment(value: true, label: Text('URL 模式'), icon: Icon(Icons.link)),
                ButtonSegment(value: false, label: Text('IP 模式'), icon: Icon(Icons.computer)),
              ],
              selected: {_useUrlMode},
              onSelectionChanged: (Set<bool> selection) {
                setState(() => _useUrlMode = selection.first);
              },
            ),
            const SizedBox(height: 24),

            // ── URL 模式 ────────────────────────────────────────────────────
            if (_useUrlMode) ...[
              const Text('伺服器 URL',
                  style: TextStyle(fontSize: 16, color: Colors.white70)),
              const SizedBox(height: 8),
              TextField(
                controller: _urlCtrl,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  hintText: '例如：https://xxxx-8081.devtunnels.ms',
                  prefixIcon: Icon(Icons.link),
                ),
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.blue.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.blue.withOpacity(0.3)),
                ),
                child: const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('💡 VSCode Dev Tunnels 使用方式：',
                        style: TextStyle(fontWeight: FontWeight.bold, color: Colors.blue)),
                    SizedBox(height: 4),
                    Text('1. 在 VSCode 中開啟 Port Forwarding',
                        style: TextStyle(color: Colors.white70, fontSize: 12)),
                    Text('2. 將本地 8081 port 設為 Public',
                        style: TextStyle(color: Colors.white70, fontSize: 12)),
                    Text('3. 複製產生的 URL（例如 https://xxx.devtunnels.ms）',
                        style: TextStyle(color: Colors.white70, fontSize: 12)),
                    Text('4. 貼上到上方欄位即可連線',
                        style: TextStyle(color: Colors.white70, fontSize: 12)),
                  ],
                ),
              ),
            ],

            // ── IP 模式 ──────────────────────────────────────────────────────
            if (!_useUrlMode) ...[
              const Text('伺服器 IP 位址',
                  style: TextStyle(fontSize: 16, color: Colors.white70)),
              const SizedBox(height: 8),
              TextField(
                controller: _hostCtrl,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
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
                controller: _portCtrl,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  hintText: '預設 8081',
                  prefixIcon: Icon(Icons.settings_ethernet),
                ),
              ),
              const SizedBox(height: 12),
              // 模擬器快速填入提示
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
              const SizedBox(height: 8),
              // TLS 開關
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
            ],

            const SizedBox(height: 16),

            // ── 目前連線狀態 ──────────────────────────────────────────────────
            Builder(
              builder: (context) {
                final app = context.watch<AppProvider>();
                final displayUrl = app.baseUrl.isNotEmpty
                    ? app.baseUrl
                    : '${app.host}:${app.port}';
                return Text(
                  '目前連線：$displayUrl',
                  style: const TextStyle(color: Colors.white54, fontSize: 14),
                );
              },
            ),

            const SizedBox(height: 24),

            // ── 儲存按鈕 ──────────────────────────────────────────────────────
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
