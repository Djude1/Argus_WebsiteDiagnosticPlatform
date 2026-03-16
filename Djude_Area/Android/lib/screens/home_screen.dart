// lib/screens/home_screen.dart
// 前台主畫面：視障友善，不需登入即可使用所有導航功能

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/theme.dart';
import '../providers/auth_provider.dart';
import '../providers/app_provider.dart';
import '../widgets/nav_button.dart';
import '../widgets/status_banner.dart';
import 'ar_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _scrollCtrl = ScrollController();

  @override
  void initState() {
    super.initState();
    context.read<AppProvider>().addListener(_scrollToBottom);
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    context.read<AppProvider>().removeListener(_scrollToBottom);
    _scrollCtrl.dispose();
    super.dispose();
  }

  /// 啟動導航功能後跳到 AR 畫面
  Future<void> _startAndShowAr(
      Future<void> Function() startFn, String title) async {
    await startFn();
    if (!mounted) return;
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => ArScreen(title: title)),
    );
  }

  Future<void> _showItemSearchDialog() async {
    final ctrl = TextEditingController();
    final result = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppTheme.surface,
        title: const Text('找什麼物品？', style: TextStyle(fontSize: 20)),
        content: TextField(
          controller:      ctrl,
          autofocus:       true,
          textInputAction: TextInputAction.done,
          onSubmitted:     (v) => Navigator.pop(ctx, v),
          decoration: const InputDecoration(hintText: '例如：手機、眼鏡、鑰匙'),
          style: const TextStyle(fontSize: 18),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx),
              child: const Text('取消')),
          ElevatedButton(
              onPressed: () => Navigator.pop(ctx, ctrl.text.trim()),
              child: const Text('開始尋找')),
        ],
      ),
    );
    if (result != null && result.isNotEmpty && mounted) {
      final app = context.read<AppProvider>();
      await app.startItemSearch(result);
      if (mounted) {
        Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => ArScreen(title: '找物品：$result')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final app      = context.watch<AppProvider>();
    final auth     = context.watch<AuthProvider>();
    final navState = app.navState;

    return Scaffold(
      appBar: AppBar(
        title: const Text('AI 智慧眼鏡'),
        actions: [
          // 緊急連絡人
          Semantics(
            label: '緊急連絡人',
            button: true,
            child: IconButton(
              icon: const Icon(Icons.contacts, size: 28),
              tooltip: '緊急連絡人',
              onPressed: () => Navigator.pushNamed(context, '/contacts'),
            ),
          ),
          // 設定
          Semantics(
            label: '伺服器設定',
            button: true,
            child: IconButton(
              icon: const Icon(Icons.settings, size: 28),
              tooltip: '設定',
              onPressed: () => Navigator.pushNamed(context, '/settings'),
            ),
          ),
          // 後台（已登入才顯示管理入口，否則只有小鎖圖示）
          if (auth.isLoggedIn)
            Semantics(
              label: '管理後台',
              button: true,
              child: IconButton(
                icon: const Icon(Icons.admin_panel_settings, size: 28),
                tooltip: '後台管理',
                onPressed: () => Navigator.pushNamed(context, '/admin'),
              ),
            )
          else
            // 長按進入後台登入（不顯眼的小鎖）
            Semantics(
              label: '管理後台登入',
              button: true,
              child: GestureDetector(
                onLongPress: () =>
                    Navigator.pushNamed(context, '/admin_login'),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Icon(Icons.lock_outline,
                      size: 22, color: Colors.white24),
                ),
              ),
            ),
        ],
      ),
      body: Column(
        children: [
          // ── 狀態橫幅 ────────────────────────────────────────────────────
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
            child: StatusBanner(
              navStateLabel: app.navStateLabel,
              connected:     app.connected,
            ),
          ),

          // ── 5 大功能按鈕 ─────────────────────────────────────────────────
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              children: [
                NavButton(
                  label:          '盲道導航',
                  semanticsLabel: '開始盲道導航，偵測前方盲道並語音引導',
                  icon:    Icons.navigation,
                  color:   AppTheme.colorBlindpath,
                  isActive: navState == 'BLINDPATH_NAV',
                  onPressed: app.connected
                      ? () => _startAndShowAr(app.startBlindpath, '盲道導航')
                      : null,
                ),
                const SizedBox(height: 10),
                NavButton(
                  label:          '過馬路',
                  semanticsLabel: '開始過馬路，偵測斑馬線與紅綠燈',
                  icon:    Icons.directions_walk,
                  color:   AppTheme.colorCrossing,
                  isActive: ['CROSSING', 'SEEKING_CROSSWALK',
                    'WAIT_TRAFFIC_LIGHT', 'SEEKING_NEXT_BLINDPATH']
                      .contains(navState),
                  onPressed: app.connected
                      ? () => _startAndShowAr(app.startCrossing, '過馬路')
                      : null,
                ),
                const SizedBox(height: 10),
                NavButton(
                  label:          '紅綠燈偵測',
                  semanticsLabel: '開始紅綠燈偵測，語音告知燈號狀態',
                  icon:    Icons.traffic,
                  color:   AppTheme.colorTrafficLight,
                  isActive: navState == 'TRAFFIC_LIGHT_DETECTION',
                  onPressed: app.connected
                      ? () => _startAndShowAr(app.startTrafficLight, '紅綠燈偵測')
                      : null,
                ),
                const SizedBox(height: 10),
                NavButton(
                  label:          '找物品',
                  semanticsLabel: '開始尋找物品，說出物品名稱或點擊輸入',
                  icon:    Icons.search,
                  color:   AppTheme.colorItemSearch,
                  isActive: navState == 'ITEM_SEARCH',
                  onPressed: app.connected ? _showItemSearchDialog : null,
                ),
                const SizedBox(height: 10),
                NavButton(
                  label:          '停止',
                  semanticsLabel: '停止目前所有導航功能',
                  icon:    Icons.stop_circle,
                  color:   AppTheme.colorStop,
                  isActive: false,
                  onPressed: app.connected ? () => app.stopNavigation() : null,
                ),
              ],
            ),
          ),

          // ── 訊息記錄 ─────────────────────────────────────────────────────
          Expanded(
            child: Container(
              margin: const EdgeInsets.fromLTRB(12, 0, 12, 12),
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: AppTheme.surface,
                borderRadius: BorderRadius.circular(12),
              ),
              child: app.messages.isEmpty
                  ? const Center(
                      child: Text('等待語音訊息…',
                          style: TextStyle(
                              color: Colors.white38, fontSize: 16)),
                    )
                  : ListView.builder(
                      controller:  _scrollCtrl,
                      itemCount:   app.messages.length,
                      itemBuilder: (_, i) => Padding(
                        padding: const EdgeInsets.symmetric(vertical: 2),
                        child: Text(app.messages[i],
                            style: const TextStyle(
                                fontSize: 14, color: Colors.white70)),
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }
}
