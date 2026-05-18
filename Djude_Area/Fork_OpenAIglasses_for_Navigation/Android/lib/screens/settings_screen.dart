// lib/screens/settings_screen.dart
// 伺服器連線設定：單一網址欄位 + 快速連線按鈕

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';
import '../core/constants.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _urlCtrl = TextEditingController();
  bool _connecting = false;

  @override
  void initState() {
    super.initState();
    final app = context.read<AppProvider>();
    // 預填目前設定
    if (app.baseUrl.isNotEmpty) {
      _urlCtrl.text = app.baseUrl;
    } else if (app.host.isNotEmpty) {
      final scheme = app.secure ? 'https' : 'http';
      _urlCtrl.text = '$scheme://${app.host}:${app.port}';
    }

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        context.read<AppProvider>().speak(
          '伺服器連線設定。輸入網址後點擊立即連接。往左滑動返回首頁。',
        );
      }
    });
  }

  @override
  void dispose() {
    _urlCtrl.dispose();
    super.dispose();
  }

  // ── 連接邏輯 ─────────────────────────────────────────────────────────────
  Future<void> _connect() async {
    FocusScope.of(context).unfocus();

    var input = _urlCtrl.text.trim();
    if (input.isEmpty) {
      _showSnack('請輸入伺服器網址或 IP', isError: true);
      return;
    }

    // 自動補 scheme：IP/localhost → http，域名 → https（Cloudflare 等公網 301 重導 https，
    // Dart HttpClient 遇到 301 會將 POST 降為 GET，導致伺服器回 405）
    if (!input.startsWith('http://') && !input.startsWith('https://')) {
      final host = input.split('/').first.split(':').first;
      final isLocal = RegExp(r'^\d+\.\d+\.\d+\.\d+$').hasMatch(host) ||
                      host == 'localhost' || host == '10.0.2.2';
      input = isLocal ? 'http://$input' : 'https://$input';
      _urlCtrl.text = input;
    }

    final parsed = AppConstants.parseUrl(input);

    setState(() => _connecting = true);
    final app = context.read<AppProvider>();
    await app.updateServerSettings(
      parsed.host, parsed.port,
      secure: parsed.secure, baseUrl: input,
    );

    bool ok = false;
    try {
      ok = await app.api.healthCheck();
    } catch (_) {}

    if (!mounted) return;
    setState(() => _connecting = false);

    if (ok) {
      HapticFeedback.mediumImpact();
      _showSnack('連線成功！', isError: false);
      final nav = Navigator.of(context);
      await app.startAllServices();
      if (!mounted) return;
      nav.pushReplacementNamed('/blind');
    } else {
      HapticFeedback.heavyImpact();
      _showSnack('無法連線到 $input', isError: true);
    }
  }

  void _showSnack(String msg, {required bool isError}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(SnackBar(
        content: Row(
          children: [
            Icon(
              isError ? Icons.error : Icons.check_circle,
              color: isError ? Colors.redAccent : Colors.greenAccent,
              size: 20,
            ),
            const SizedBox(width: 10),
            Expanded(child: Text(msg)),
          ],
        ),
        backgroundColor: isError
            ? const Color(0xFF7F1D1D)
            : const Color(0xFF1B5E20),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        duration: Duration(seconds: isError ? 4 : 2),
      ));
  }

  void _quickFill(String url) {
    setState(() => _urlCtrl.text = url);
    HapticFeedback.selectionClick();
  }

  // 斷線時返回管理員首頁；已連線時返回視障者主頁
  void _goBack() {
    debugPrint('[SettingsScreen] _goBack called, connected=${context.read<AppProvider>().connected}');
    final app = context.read<AppProvider>();
    if (app.connected) {
      Navigator.pushReplacementNamed(context, '/blind');
    } else {
      Navigator.pushReplacementNamed(context, '/home');
    }
  }

  // ── UI ───────────────────────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppProvider>();

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) { if (!didPop) _goBack(); },
      child: GestureDetector(
      onHorizontalDragEnd: (details) {
        if ((details.primaryVelocity ?? 0) > 300) _goBack();
      },
      child: Scaffold(
        backgroundColor: const Color(0xFF0A0A0A),
        body: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // ── 頂部標題列 ────────────────────────────────────────────
              _buildHeader(app),

              // ── 主要內容 ──────────────────────────────────────────────
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(20, 16, 20, 40),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _buildStatusCard(app),
                      const SizedBox(height: 24),
                      _buildUrlInput(),
                      const SizedBox(height: 16),
                      _buildConnectButton(),
                      const SizedBox(height: 24),
                      _buildQuickButtons(),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
      ), // GestureDetector
    );   // PopScope
  }

  // ── 頂部列 ─────────────────────────────────────────────────────────────
  Widget _buildHeader(AppProvider app) {
    return Container(
      color: const Color(0xFF0D0D0D),
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 20),
      child: Row(
        children: [
          InkWell(
            onTap: _goBack,
            borderRadius: BorderRadius.circular(8),
            child: const Padding(
              padding: EdgeInsets.all(4),
              child: Icon(Icons.arrow_back_ios_new,
                  size: 20, color: Colors.white54),
            ),
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Text(
              '伺服器連線設定',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
            ),
          ),
          _ConnDot(connected: app.connected),
        ],
      ),
    );
  }

  // ── 連線狀態卡片 ───────────────────────────────────────────────────────
  Widget _buildStatusCard(AppProvider app) {
    final connected = app.connected;
    final currentUrl = app.baseUrl.isNotEmpty
        ? app.baseUrl
        : (app.host.isNotEmpty ? '${app.host}:${app.port}' : '');

    return AnimatedContainer(
      duration: const Duration(milliseconds: 400),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: connected
              ? [const Color(0xFF1B5E20), const Color(0xFF0D3B14)]
              : [const Color(0xFF3E2723), const Color(0xFF1A1210)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: connected
              ? Colors.green.withAlpha(60)
              : Colors.red.withAlpha(30),
        ),
      ),
      child: Row(
        children: [
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 300),
            child: Icon(
              connected ? Icons.cloud_done_rounded : Icons.cloud_off_rounded,
              key: ValueKey(connected),
              size: 36,
              color: connected
                  ? Colors.greenAccent
                  : Colors.redAccent.shade100,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  connected ? '已連線' : '未連線',
                  style: TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.bold,
                    color: connected
                        ? Colors.greenAccent
                        : Colors.redAccent.shade100,
                  ),
                ),
                if (currentUrl.isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Text(
                    currentUrl,
                    style: TextStyle(
                      fontSize: 12,
                      color: connected ? Colors.white60 : Colors.white38,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ],
            ),
          ),
          if (connected)
            IconButton(
              onPressed: _connect,
              icon: const Icon(Icons.refresh_rounded, color: Colors.white54),
              tooltip: '重新連線',
            ),
        ],
      ),
    );
  }

  // ── 網址輸入框 ─────────────────────────────────────────────────────────
  Widget _buildUrlInput() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Row(
          children: [
            Icon(Icons.link_rounded, size: 16, color: Colors.blueAccent),
            SizedBox(width: 6),
            Text('伺服器網址 / IP',
                style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: Colors.white70)),
          ],
        ),
        const SizedBox(height: 10),
        TextField(
          controller: _urlCtrl,
          keyboardType: TextInputType.url,
          style: const TextStyle(fontSize: 15, color: Colors.white),
          onSubmitted: (_) => _connect(),
          decoration: InputDecoration(
            hintText: '網址或 IP，例如 192.168.1.100:8081',
            hintStyle: const TextStyle(color: Colors.white24, fontSize: 13),
            prefixIcon:
                const Icon(Icons.language_rounded, color: Colors.white38),
            suffixIcon: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                // 貼上
                IconButton(
                  icon: const Icon(Icons.content_paste_rounded,
                      size: 18, color: Colors.white38),
                  tooltip: '從剪貼簿貼上',
                  onPressed: () async {
                    final data =
                        await Clipboard.getData(Clipboard.kTextPlain);
                    if (data?.text != null && data!.text!.isNotEmpty) {
                      setState(() => _urlCtrl.text = data.text!.trim());
                    }
                  },
                ),
                // 清除
                if (_urlCtrl.text.isNotEmpty)
                  IconButton(
                    icon: const Icon(Icons.clear_rounded,
                        size: 18, color: Colors.white38),
                    onPressed: () => setState(() => _urlCtrl.clear()),
                  ),
              ],
            ),
            filled: true,
            fillColor: Colors.white.withAlpha(15),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide.none,
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide:
                  const BorderSide(color: Colors.blueAccent, width: 1.5),
            ),
            contentPadding: const EdgeInsets.symmetric(vertical: 16),
          ),
          onChanged: (_) => setState(() {}),
        ),
      ],
    );
  }

  // ── 連接按鈕 ──────────────────────────────────────────────────────────
  Widget _buildConnectButton() {
    return SizedBox(
      height: 54,
      child: ElevatedButton(
        onPressed: _connecting ? null : _connect,
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFF1565C0),
          disabledBackgroundColor: const Color(0xFF1565C0).withAlpha(120),
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14)),
          elevation: _connecting ? 0 : 4,
        ),
        child: _connecting
            ? const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  SizedBox(
                    width: 20, height: 20,
                    child: CircularProgressIndicator(
                        color: Colors.white70, strokeWidth: 2.5),
                  ),
                  SizedBox(width: 12),
                  Text('連線中…',
                      style: TextStyle(
                          fontSize: 17, fontWeight: FontWeight.bold)),
                ],
              )
            : const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.bolt_rounded, size: 22),
                  SizedBox(width: 8),
                  Text('立即連接',
                      style: TextStyle(
                          fontSize: 17, fontWeight: FontWeight.bold)),
                ],
              ),
      ),
    );
  }

  // ── 快速連線按鈕（永久固定）──────────────────────────────────────────
  Widget _buildQuickButtons() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('快速填入',
            style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: Colors.white38)),
        const SizedBox(height: 10),

        // 公網（點擊展開裝置選單）
        _PublicServerRow(
          selectedUrl: _urlCtrl.text,
          onSelected: _quickFill,
        ),
        const SizedBox(height: 8),

        // 模擬器
        _QuickButton(
          icon: Icons.phone_android_rounded,
          label: 'Android 模擬器',
          url: 'http://10.0.2.2:8081',
          isSelected: _urlCtrl.text == 'http://10.0.2.2:8081',
          onTap: () => _quickFill('http://10.0.2.2:8081'),
        ),
        const SizedBox(height: 8),

        // 本機
        _QuickButton(
          icon: Icons.computer_rounded,
          label: '本機',
          url: 'http://localhost:8081',
          isSelected: _urlCtrl.text == 'http://localhost:8081',
          onTap: () => _quickFill('http://localhost:8081'),
        ),
        const SizedBox(height: 8),

        // 區網 IP
        _QuickButton(
          icon: Icons.wifi_rounded,
          label: '區網 IP（範例）',
          url: 'http://192.168.1.100:8081',
          isSelected: _urlCtrl.text == 'http://192.168.1.100:8081',
          onTap: () => _quickFill('http://192.168.1.100:8081'),
        ),
      ],
    );
  }
}

// ════════════════════════════════════════════════════════════════════════════
// 子元件
// ════════════════════════════════════════════════════════════════════════════

/// 右上角連線指示燈（帶呼吸動畫）
class _ConnDot extends StatefulWidget {
  final bool connected;
  const _ConnDot({required this.connected});

  @override
  State<_ConnDot> createState() => _ConnDotState();
}

class _ConnDotState extends State<_ConnDot>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    _ctrl.addListener(_onTick);
  }

  void _onTick() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _ctrl.removeListener(_onTick);
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final glow = widget.connected ? (_ctrl.value * 0.6 + 0.4) : 0.3;
    return Container(
      width: 12,
      height: 12,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: widget.connected
            ? Colors.greenAccent.withAlpha((glow * 255).toInt())
            : Colors.redAccent.withAlpha(80),
        boxShadow: widget.connected
            ? [
                BoxShadow(
                  color: Colors.greenAccent.withAlpha((glow * 100).toInt()),
                  blurRadius: 8,
                  spreadRadius: 2,
                )
              ]
            : null,
      ),
    );
  }
}

/// 公網伺服器列——點擊彈出 bottom sheet 選 device/1~4
class _PublicServerRow extends StatelessWidget {
  static const _devices = [
    (label: '裝置 1', url: 'https://aiglasses.qzz.io/device/1/'),
    (label: '裝置 2', url: 'https://aiglasses.qzz.io/device/2/'),
    (label: '裝置 3', url: 'https://aiglasses.qzz.io/device/3/'),
    (label: '裝置 4', url: 'https://aiglasses.qzz.io/device/4/'),
  ];

  final String selectedUrl;
  final void Function(String) onSelected;

  const _PublicServerRow({required this.selectedUrl, required this.onSelected});

  bool get _anySelected => _devices.any((d) => d.url == selectedUrl);

  void _showPicker(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: const Color(0xFF1A1A1A),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 8),
            Container(
              width: 36, height: 4,
              decoration: BoxDecoration(
                color: Colors.white24,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 12),
            const Text(
              '選擇公網伺服器',
              style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.bold,
                color: Colors.white70,
              ),
            ),
            const SizedBox(height: 4),
            for (final device in _devices)
              ListTile(
                leading: Icon(
                  Icons.dns_rounded,
                  size: 20,
                  color: selectedUrl == device.url
                      ? Colors.blueAccent
                      : Colors.white38,
                ),
                title: Text(
                  device.label,
                  style: TextStyle(
                    color: selectedUrl == device.url
                        ? Colors.white
                        : Colors.white70,
                    fontWeight: selectedUrl == device.url
                        ? FontWeight.bold
                        : FontWeight.normal,
                  ),
                ),
                subtitle: Text(
                  device.url,
                  style: const TextStyle(color: Colors.white30, fontSize: 11),
                ),
                trailing: selectedUrl == device.url
                    ? const Icon(Icons.check_circle_rounded,
                        size: 18, color: Colors.blueAccent)
                    : null,
                onTap: () {
                  Navigator.pop(ctx);
                  onSelected(device.url);
                },
              ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      color: _anySelected
          ? Colors.blueAccent.withAlpha(25)
          : Colors.white.withAlpha(8),
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: () => _showPicker(context),
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          child: Row(
            children: [
              Icon(Icons.public_rounded,
                  size: 20,
                  color: _anySelected ? Colors.blueAccent : Colors.white38),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '公網伺服器',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        color: _anySelected ? Colors.white : Colors.white70,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _anySelected ? selectedUrl : '點擊選擇裝置 1–4',
                      style: TextStyle(
                        fontSize: 11,
                        color: _anySelected ? Colors.blueAccent : Colors.white30,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              Icon(
                Icons.chevron_right_rounded,
                size: 20,
                color: _anySelected ? Colors.blueAccent : Colors.white24,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 快速連線按鈕（整列可點擊，點擊填入網址）
class _QuickButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final String url;
  final bool isSelected;
  final VoidCallback onTap;

  const _QuickButton({
    required this.icon,
    required this.label,
    required this.url,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: isSelected
          ? Colors.blueAccent.withAlpha(25)
          : Colors.white.withAlpha(8),
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          child: Row(
            children: [
              Icon(icon,
                  size: 20,
                  color:
                      isSelected ? Colors.blueAccent : Colors.white38),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label,
                        style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                            color: isSelected
                                ? Colors.white
                                : Colors.white70)),
                    const SizedBox(height: 2),
                    Text(url,
                        style: TextStyle(
                            fontSize: 11,
                            color: isSelected
                                ? Colors.blueAccent
                                : Colors.white30)),
                  ],
                ),
              ),
              if (isSelected)
                const Icon(Icons.check_circle_rounded,
                    size: 18, color: Colors.blueAccent),
            ],
          ),
        ),
      ),
    );
  }
}
