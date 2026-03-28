// lib/screens/blind_screen.dart
// 視障者專用主畫面（雙頁 PageView）
//
// 頁面 0：主功能頁
//   • 大按鈕開始 / 停止導航（點擊觸發，非 TalkBack：觸碰播報，離開執行）
//   • 底部緊急求救按鈕（同上）
//
// 頁面 1：設定頁
//   • 緊急連絡人管理
//   • 聲音播報設定（TalkBack 關閉時顯示）

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';
import 'contacts_screen.dart';
import 'emergency_select_screen.dart';
import 'emergency_countdown_screen.dart';

class BlindScreen extends StatefulWidget {
  const BlindScreen({super.key});

  @override
  State<BlindScreen> createState() => _BlindScreenState();
}

class _BlindScreenState extends State<BlindScreen>
    with WidgetsBindingObserver {
  // 頁面 0 = 主功能，頁面 1 = 設定
  final _pageController = PageController(initialPage: 0);
  int _currentPage = 0;

  // AppProvider 狀態追蹤
  String _prevNavState    = '';
  int    _prevMsgCount    = 0;
  bool?  _prevConnected;
  int    _prevImpactVersion = 0;   // 上一次消化的撞擊版本號，避免重複彈出

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final app = context.read<AppProvider>();
      _prevNavState  = app.navState;
      _prevMsgCount  = app.messageCount;
      _prevConnected = app.connected;
      app.addListener(_onAppChanged);
      _announce(app.connected
          ? 'AI智慧眼鏡已連線。向左滑動可進入設定頁面。'
          : '正在連線伺服器，請稍候。');
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    context.read<AppProvider>().removeListener(_onAppChanged);
    _pageController.dispose();
    super.dispose();
  }

  // 生命週期變更：通知 Provider 更新前台/背景狀態
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    context.read<AppProvider>().handleLifecycleState(state);
  }

  // ── 監聽 AppProvider ────────────────────────────────────────────────────
  void _onAppChanged() {
    if (!mounted) return;
    final app = context.read<AppProvider>();

    if (_prevConnected != app.connected) {
      _prevConnected = app.connected;
      _announce(app.connected ? '伺服器已連線' : '伺服器連線中斷，正在重新連線');
    }

    if (_prevNavState != app.navState) {
      final label = _navStateVoice(app.navState);
      if (label.isNotEmpty) _announce(label);
      _prevNavState = app.navState;
    }

    if (app.messageCount > _prevMsgCount) {
      final spoken = _filterMessage(app.lastMessage ?? '');
      if (spoken != null && spoken.isNotEmpty) _announce(spoken);
      _prevMsgCount = app.messageCount;
    }

    // ── 消化待辦撞擊事件（前台直接觸發 / 背景返回後補觸發）───────────────
    // 以版本號比對取代力道值比對，確保相同力道的撞擊也能重複觸發
    final impact        = app.pendingImpactMagnitude;
    final impactVersion = app.impactVersion;
    if (impact > 0 && impactVersion != _prevImpactVersion) {
      _prevImpactVersion = impactVersion;
      app.clearPendingImpact();
      if (app.contacts.isNotEmpty) {
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => EmergencyCountdownScreen(
              magnitude: impact,
              onOutcome: (outcome) =>
                  _handleImpactOutcome(impact, outcome),
            ),
          ),
        );
      }
    }
  }

  // ── 撞擊倒數結束後：詢問是否誤判，再回報伺服器 ──────────────────────────
  Future<void> _handleImpactOutcome(double magnitude, String outcome) async {
    if (!mounted) return;
    final app = context.read<AppProvider>();

    // 等畫面回到 BlindScreen 後再彈出對話框
    await Future.delayed(const Duration(milliseconds: 400));
    if (!mounted) return;

    final isFalse = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A2E),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Text(
          '這次偵測是誤判嗎？',
          style: TextStyle(
              fontSize: 20, fontWeight: FontWeight.bold, color: Colors.white),
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '撞擊力道：${magnitude.toStringAsFixed(1)} m/s²',
              style: const TextStyle(fontSize: 14, color: Colors.white54),
            ),
            const SizedBox(height: 8),
            const Text(
              '您的回饋將幫助我們調整偵測靈敏度。',
              style: TextStyle(fontSize: 14, color: Colors.white70),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('是，這是誤判',
                style: TextStyle(color: Colors.orangeAccent, fontSize: 16)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF1B5E20),
            ),
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('不是，真的摔倒了',
                style: TextStyle(color: Colors.white, fontSize: 16)),
          ),
        ],
      ),
    );

    if (isFalse == null || !mounted) return;
    // 回報伺服器（含誤判旗標）
    app.reportImpactEvent(magnitude, outcome, isFalsePositive: isFalse);
    app.speak(isFalse ? '已記錄為誤判，感謝回饋' : '已記錄，請注意安全');
  }

  void _announce(String text) =>
      context.read<AppProvider>().speak(text);

  // ── 導航按鈕邏輯（GPS 導航）────────────────────────────────────────────
  Future<void> _doNavAction() async {
    HapticFeedback.heavyImpact();
    final app = context.read<AppProvider>();
    if (!app.connected) { _announce('伺服器未連線，請稍候'); return; }
    if (app.gpsNavActive) {
      // GPS 導航進行中 → 只停 GPS，保留避障
      await app.stopGpsNavigation();
    } else {
      // 進入目的地選擇畫面
      if (mounted) {
        Navigator.pushNamed(context, '/nav_dest');
      }
    }
  }

  // ── 避障功能（獨立於 GPS 導航）──────────────────────────────────────────
  Future<void> _doObstacleAvoidance() async {
    HapticFeedback.heavyImpact();
    final app = context.read<AppProvider>();
    if (!app.connected) { _announce('伺服器未連線，請稍候'); return; }
    if (_isNavigating(app.navState)) {
      // 伺服器端有避障在跑 → 停止避障
      await app.stopObstacleAvoidance();
    } else {
      await app.startBlindpath();
    }
  }

  // ── 手動緊急求救：固定顯示兩位聯絡人選擇畫面 ──────────────────────────
  Future<void> _doEmergency() async {
    HapticFeedback.heavyImpact();
    if (!mounted) return;
    Navigator.push(context,
        MaterialPageRoute(builder: (_) => const EmergencySelectScreen()));
  }

  Future<void> _switchToDeveloper() async {
    HapticFeedback.heavyImpact();
    await context.read<AppProvider>().stopNavigation();
    if (mounted) Navigator.pushReplacementNamed(context, '/home');
  }

  // ── 頁面切換 ─────────────────────────────────────────────────────────────

  // ── 輔助 ─────────────────────────────────────────────────────────────────
  bool _isNavigating(String s) =>
      !['IDLE', 'CHAT', ''].contains(s);

  String _navStateVoice(String s) {
    const m = {
      'BLINDPATH_NAV':          '避障導航已開始',
      'SEEKING_CROSSWALK':      '正在靠近斑馬線',
      'WAIT_TRAFFIC_LIGHT':     '已到達斑馬線，等待綠燈',
      'CROSSING':               '綠燈，開始過馬路',
      'SEEKING_NEXT_BLINDPATH': '過馬路完成，尋找下一段盲道',
      'RECOVERY':               '環境複雜，正在恢復導航',
      'ITEM_SEARCH':            '物品搜尋模式',
      'IDLE':                   '導航已停止',
    };
    return m[s] ?? '';
  }

  // 導航指引文字簡化對照表（長句 → 短指令）
  static const _navSimplify = <String, String>{
    // ── 導航動作簡化 ───────────────────────────────────
    '请向左转动。':          '左转',
    '请向右转动。':          '右转',
    '请向左平移。':          '左移',
    '请向右平移。':          '右移',
    '请向左微调，对准盲道。': '左微调',
    '请向右微调，对准盲道。': '右微调',
    '请继续向左平移。':      '继续左移',
    '请继续向右平移。':      '继续右移',
    '方向已对正！现在校准位置。': '方向正确',
    '校准完成！您已在盲道上，开始前行。': '前行',
    // ── 技術訊息：不播報 ───────────────────────────────
    '路径特征提取失败':      '',
    // ── 無盲道狀態提示（直接播報，不簡化）───────────────
    '找不到盲道':                    '找不到盲道',
    '找不到盲道，請左右移動尋找':     '找不到盲道，請左右移動尋找',
    '此地已確認沒有盲道，目前只作避障處理': '此地沒有盲道，切換避障模式',
    '重新找到盲道，恢復導航':         '重新找到盲道',
  };

  String? _filterMessage(String msg) {
    if (msg.contains('[ASR]') || msg.contains('[USER]'))   return null;
    if (msg.contains('攝影機') || msg.contains('麥克風'))   return null;
    if (msg.contains('WebSocket') || msg.contains('連線')) return null;
    if (msg.contains('[狀態]'))                            return null;
    // 導航指引（伺服器以 [导航] 前綴廣播）→ 直接由 APP TTS 播報
    if (msg.contains('[导航]')) {
      final text = msg.replaceAll(RegExp(r'^\[导航\]\s*'), '').trim();
      // 查表簡化；若對照結果為空字串則不播報
      final simplified = _navSimplify[text];
      if (simplified != null) return simplified.isEmpty ? null : simplified;
      return text;
    }
    // 系統訊息（相容繁體 [系統] 與簡體 [系统]）
    if (msg.contains('[系統]') || msg.contains('[系统]')) {
      return msg.replaceAll(RegExp(r'^\[系[統统]\]\s*'), '');
    }
    return null;
  }

  // ── Build ────────────────────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppProvider>();
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Stack(
          children: [
            PageView(
              controller: _pageController,
              onPageChanged: (i) {
                HapticFeedback.selectionClick();
                setState(() => _currentPage = i);
                if (i == 0) _announce('首頁。導航、閱讀、緊急求救。');
                if (i == 1) _announce('設定頁面。有緊急聯絡人、語音開關、語音速度、報位方式。向右滑動返回首頁。');
              },
              children: [
                // ── 頁面 0：主功能（預設）─────────────────────────────────
                _MainPage(
                  app:                  app,
                  onNavAction:          _doNavAction,
                  onObstacleAvoidance:  _doObstacleAvoidance,
                  onEmergency:          _doEmergency,
                  onAnnounce:           _announce,
                ),
                // ── 頁面 1：設定（左滑進入）───────────────────────────────
                _SettingsPage(
                  onSwitchDev: _switchToDeveloper,
                  onAnnounce:  _announce,
                ),
              ],
            ),

            // ── 頁面指示點（兩頁都顯示，置底中央）────────────────────────
            Positioned(
              bottom: 10,
              left: 0, right: 0,
              child: _PageDots(current: _currentPage, total: 2),
            ),
          ],
        ),
      ),
    );
  }
}

// ════════════════════════════════════════════════════════════════════════════
// 頁面 0：首頁（主功能）
// ════════════════════════════════════════════════════════════════════════════
class _MainPage extends StatelessWidget {
  final AppProvider app;
  final VoidCallback onNavAction;
  final VoidCallback onObstacleAvoidance;
  final VoidCallback onEmergency;
  final void Function(String) onAnnounce;

  const _MainPage({
    required this.app,
    required this.onNavAction,
    required this.onObstacleAvoidance,
    required this.onEmergency,
    required this.onAnnounce,
  });

  /// 伺服器端有避障/導航功能在運作
  bool get _isObstacleActive => !['IDLE', 'CHAT', ''].contains(app.navState);
  /// GPS 導航（Google Maps 背景語音）在運作
  bool get _isGpsActive => app.gpsNavActive;

  /// 距離文字格式化
  String _distanceText(double meters) {
    if (meters < 1000) return '${meters.toStringAsFixed(0)}公尺';
    return '${(meters / 1000).toStringAsFixed(1)}公里';
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // ── 頂部狀態色條 ───────────────────────────────────────────────
        _StatusBar(connected: app.connected, navState: app.navState),

        // ── 頁面標題列 ─────────────────────────────────────────────────
        Container(
          color: const Color(0xFF0D0D0D),
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 20),
          child: const Row(
            children: [
              Text(
                '首頁',
                style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                    color: Colors.white),
              ),
              Spacer(),
              Text(
                '向左滑動進入設定',
                style: TextStyle(fontSize: 13, color: Colors.white38),
              ),
            ],
          ),
        ),

        // ── 主導航大按鈕（佔約 42%）──────────────────────────────────
        Expanded(
          flex: 42,
          child: _TriggerButton(
            semanticsLabel: !app.connected
                ? '伺服器未連線，無法導航'
                : _isGpsActive
                    ? '停止 GPS，點擊結束 GPS 導航'
                    : 'GPS 導航，點擊選擇目的地',
            onAction: onNavAction,
            onFocus: () => onAnnounce(
              !app.connected
                  ? '伺服器未連線'
                  : _isGpsActive ? '停止 GPS' : 'GPS 導航',
            ),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              color: !app.connected
                  ? const Color(0xFF212121)
                  : _isGpsActive
                      ? const Color(0xFFB71C1C)
                      : const Color(0xFF1565C0),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    !app.connected
                        ? Icons.wifi_off
                        : _isGpsActive
                            ? Icons.stop_circle_outlined
                            : Icons.map,
                    size: 80,
                    color: app.connected ? Colors.white : Colors.white38,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    !app.connected
                        ? '連線中…'
                        : _isGpsActive
                            ? '停止 GPS'
                            : 'GPS 導航',
                    style: TextStyle(
                      fontSize: 42,
                      fontWeight: FontWeight.bold,
                      color: app.connected ? Colors.white : Colors.white38,
                    ),
                  ),
                  if (_isGpsActive) ...[
                    const SizedBox(height: 8),
                    // GPS 導航距離提示
                    if (app.gpsDistance < double.infinity)
                      Semantics(
                        label: '距離目的地 ${_distanceText(app.gpsDistance)}',
                        child: Text(
                          '距離目的地 ${_distanceText(app.gpsDistance)}',
                          style: const TextStyle(
                              fontSize: 22, color: Colors.yellowAccent),
                        ),
                      )
                    else
                      const Text(
                        '正在取得位置…',
                        style: TextStyle(fontSize: 20, color: Colors.white54),
                      ),
                  ],
                ],
              ),
            ),
          ),
        ),

        // ── 避障功能按鈕（佔約 15%）──────────────────────────────────
        Expanded(
          flex: 15,
          child: _TriggerButton(
            semanticsLabel: !app.connected
                ? '伺服器未連線'
                : _isObstacleActive
                    ? '避障導航運作中，點擊停止'
                    : '避障導航，點擊開啟障礙物偵測',
            onAction: onObstacleAvoidance,
            onFocus: () => onAnnounce(
              _isObstacleActive ? '停止避障導航' : '避障導航',
            ),
            child: Container(
              color: _isObstacleActive
                  ? const Color(0xFF880E4F)
                  : const Color(0xFF4A148C),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    _isObstacleActive ? Icons.stop : Icons.shield,
                    size: 32, color: Colors.white,
                  ),
                  const SizedBox(width: 12),
                  Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _isObstacleActive ? '停止避障導航' : '避障導航',
                        style: const TextStyle(
                            fontSize: 24,
                            fontWeight: FontWeight.bold,
                            color: Colors.white),
                      ),
                      Text(
                        _isObstacleActive
                            ? '${_stateLabel(app.navState)}，點擊停止'
                            : '盲道導航＋障礙物偵測',
                        style: const TextStyle(
                            fontSize: 12, color: Colors.white60),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),

        // ── 文件閱讀按鈕（佔約 12%）──────────────────────────────────
        Expanded(
          flex: 12,
          child: _TriggerButton(
            semanticsLabel: '文件閱讀，拍照辨識文件語音朗讀',
            onAction: () => Navigator.pushNamed(context, '/read'),
            onFocus: () => onAnnounce('文件閱讀'),
            child: Container(
              color: const Color(0xFF00695C),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.document_scanner, size: 32, color: Colors.white),
                  SizedBox(width: 12),
                  Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('文件閱讀',
                          style: TextStyle(
                              fontSize: 24,
                              fontWeight: FontWeight.bold,
                              color: Colors.white)),
                      Text('拍照辨識，語音朗讀',
                          style: TextStyle(
                              fontSize: 12, color: Colors.white60)),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),

        // ── 緊急求救按鈕（佔約 18%）──────────────────────────────────
        Expanded(
          flex: 18,
          child: _TriggerButton(
            semanticsLabel: '緊急求救，點擊呼叫緊急聯絡人',
            onAction: onEmergency,
            onFocus: () => onAnnounce('緊急求救'),
            child: Container(
              color: const Color(0xFFE65100),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.phone, size: 38, color: Colors.white),
                  SizedBox(width: 14),
                  Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('緊急求救',
                          style: TextStyle(
                              fontSize: 28,
                              fontWeight: FontWeight.bold,
                              color: Colors.white)),
                      Text('點擊觸發',
                          style: TextStyle(
                              fontSize: 13, color: Colors.white60)),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),

        // ── 底部空間（留給頁面指示點）────────────────────────────────
        const SizedBox(height: 30),
      ],
    );
  }

  String _stateLabel(String s) {
    const m = {
      'BLINDPATH_NAV':          '避障導航中',
      'SEEKING_CROSSWALK':      '靠近斑馬線',
      'WAIT_TRAFFIC_LIGHT':     '等待綠燈',
      'CROSSING':               '過馬路中',
      'SEEKING_NEXT_BLINDPATH': '尋找下一段盲道',
      'RECOVERY':               '恢復中',
    };
    return m[s] ?? s;
  }
}

// ════════════════════════════════════════════════════════════════════════════
// 頁面 1：設定（移除觸發方式選項，簡化為固定點擊觸發）
// ════════════════════════════════════════════════════════════════════════════
class _SettingsPage extends StatefulWidget {
  final VoidCallback onSwitchDev;
  final void Function(String) onAnnounce;

  const _SettingsPage({
    required this.onSwitchDev,
    required this.onAnnounce,
  });

  @override
  State<_SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<_SettingsPage> {
  // 語速循環：0.35 慢 → 0.5 正常 → 0.7 快 → 1.0 超快 → 0.35 …
  static const _rates      = [0.35, 0.5, 0.7, 1.0];
  static const _rateLabels = ['慢速', '正常', '快速', '超快速'];

  bool _isDevMode = false;

  @override
  void initState() {
    super.initState();
    _checkDevMode();
  }

  Future<void> _checkDevMode() async {
    try {
      const channel = MethodChannel('com.aiglasses/app_control');
      final result = await channel.invokeMethod<bool>('isDeveloperMode');
      debugPrint('[Settings] isDeveloperMode = $result');
      if (mounted) setState(() => _isDevMode = result ?? false);
    } catch (e) {
      debugPrint('[Settings] _checkDevMode 失敗: $e');
    }
  }

  String _rateLabel(double rate) {
    if (rate <= 0.35) return '慢速';
    if (rate <= 0.5)  return '正常';
    if (rate <= 0.7)  return '快速';
    return '超快速';
  }

  double _nextRate(double current) {
    final idx = _rates.indexWhere((r) => (r - current).abs() < 0.01);
    return _rates[(idx + 1) % _rates.length];
  }

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppProvider>();

    return SafeArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // ── 頂部提示 ──────────────────────────────────────────────────
          Container(
            color: Colors.black,
            padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 20),
            child: const Text(
              '設定　　向右滑動返回主功能',
              style: TextStyle(fontSize: 20, color: Colors.white54),
            ),
          ),

          // ── 色塊清單 ──────────────────────────────────────────────────
          Expanded(
            child: ListView(
              padding: EdgeInsets.zero,
              children: [

                // ── 緊急連絡人 ──────────────────────────────────────────
                _BigBlock(
                  label: '緊急連絡人',
                  color: const Color(0xFF1A237E),
                  onAnnounce: widget.onAnnounce,
                  onAction: () => Navigator.push(context,
                      MaterialPageRoute(builder: (_) => const ContactsScreen())),
                ),

                const SizedBox(height: 4),

                // ── APP 語音開關 ─────────────────────────────────────────
                _BigBlock(
                  label: 'APP 語音：${app.ttsEnabled ? '開啟' : '關閉'}',
                  sublabel: '點擊可${app.ttsEnabled ? '關閉' : '開啟'}語音播報',
                  color: app.ttsEnabled
                      ? const Color(0xFF2E7D32)
                      : const Color(0xFF424242),
                  onAnnounce: widget.onAnnounce,
                  onAction: () {
                    final next = !app.ttsEnabled;
                    if (!next) widget.onAnnounce('APP語音已關閉');
                    app.setTtsEnabled(next);
                    if (next) widget.onAnnounce('APP語音已開啟');
                  },
                ),

                const SizedBox(height: 4),

                // ── 語速設定（循環切換）──────────────────────────────────
                _BigBlock(
                  label: '語音速度：${_rateLabel(app.ttsSpeechRate)}',
                  sublabel: '點擊切換為${_rateLabels[(_rates.indexWhere((r) => (r - app.ttsSpeechRate).abs() < 0.01) + 1) % 4]}',
                  color: const Color(0xFF4A148C),
                  onAnnounce: widget.onAnnounce,
                  onAction: () {
                    final next = _nextRate(app.ttsSpeechRate);
                    app.setTtsSpeechRate(next);
                    widget.onAnnounce('語音速度已切換為${_rateLabel(next)}');
                  },
                ),

                const SizedBox(height: 4),

                // ── 方位播報模式（點擊循環切換）─────────────────────────
                _BigBlock(
                  label: '報位方式：${app.positionMode == 'clock' ? '時鐘方向' : '前後左右'}',
                  sublabel: app.positionMode == 'clock'
                      ? '例：在你的3點鐘方向　點擊切換'
                      : '例：在你的左前方　　　點擊切換',
                  color: const Color(0xFF1565C0),
                  onAnnounce: widget.onAnnounce,
                  onAction: () {
                    final next =
                        app.positionMode == 'clock' ? 'cardinal' : 'clock';
                    app.setPositionMode(next);
                    widget.onAnnounce(
                      next == 'clock'
                          ? '已切換為時鐘方向報位'
                          : '已切換為前後左右報位',
                    );
                  },
                ),

                // ── 切換開發者模式（僅手機開啟開發人員選項時顯示）───
                if (_isDevMode) ...[
                  const SizedBox(height: 4),
                  _BigBlock(
                    label: '開發者模式',
                    color: const Color(0xFF212121),
                    onAnnounce: widget.onAnnounce,
                    onAction: widget.onSwitchDev,
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ════════════════════════════════════════════════════════════════════════════
// 點擊觸發的大按鈕包裝元件
// • 非 TalkBack：手指按下播報標籤（探索），手指離開執行動作，中途可滑走取消
// • TalkBack：單擊聚焦 TalkBack 讀標籤，雙擊執行動作（標準 TalkBack 互動）
// 移除長按/雙擊選項，避免與 TalkBack 手勢衝突
// ════════════════════════════════════════════════════════════════════════════
class _TriggerButton extends StatelessWidget {
  final String semanticsLabel;
  final VoidCallback onAction;
  final VoidCallback? onFocus;  // 非 TalkBack 手指觸碰時播報
  final Widget child;

  const _TriggerButton({
    required this.semanticsLabel,
    required this.onAction,
    required this.child,
    this.onFocus,
  });

  @override
  Widget build(BuildContext context) {
    final isTalkBackOn = MediaQuery.of(context).accessibleNavigation;
    return Semantics(
      label: semanticsLabel,
      button: true,
      onTap: onAction,
      child: GestureDetector(
        onTap: () {
          HapticFeedback.heavyImpact();
          onAction();
        },
        // 非 TalkBack：手指按下播報標籤（讓使用者確認後再離開觸發）
        onTapDown: (!isTalkBackOn && onFocus != null)
            ? (_) => onFocus!()
            : null,
        child: child,
      ),
    );
  }
}

// ════════════════════════════════════════════════════════════════════════════
// 共用 UI 小元件
// ════════════════════════════════════════════════════════════════════════════

class _StatusBar extends StatelessWidget {
  final bool connected;
  final String navState;
  const _StatusBar({required this.connected, required this.navState});

  @override
  Widget build(BuildContext context) {
    final navigating = !['IDLE', 'CHAT', ''].contains(navState);
    Color c = !connected
        ? Colors.grey.shade800
        : navigating
            ? Colors.green.shade700
            : Colors.blue.shade900;
    return AnimatedContainer(
        duration: const Duration(milliseconds: 400), height: 6, color: c);
  }
}

class _PageDots extends StatelessWidget {
  final int current;
  final int total;
  const _PageDots({required this.current, required this.total});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(total, (i) {
        final active = i == current;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          margin: const EdgeInsets.symmetric(horizontal: 5),
          width:  active ? 18 : 8,
          height: 8,
          decoration: BoxDecoration(
            color: active ? Colors.white70 : Colors.white24,
            borderRadius: BorderRadius.circular(4),
          ),
        );
      }),
    );
  }
}

// ── 超大色塊按鈕（視障者設定頁專用）────────────────────────────────────────
// 非 TalkBack：手指按下播報標籤（探索，防誤觸），手指離開執行動作
// TalkBack：單擊聚焦 TalkBack 讀 Semantics，雙擊執行（標準互動）
class _BigBlock extends StatelessWidget {
  final String label;
  final String sublabel;
  final Color color;
  final VoidCallback onAction;
  final void Function(String)? onAnnounce;

  const _BigBlock({
    required this.label,
    required this.color,
    required this.onAction,
    this.sublabel = '',
    this.onAnnounce,
  });

  @override
  Widget build(BuildContext context) {
    final isTalkBackOn = MediaQuery.of(context).accessibleNavigation;
    final semanticsText = sublabel.isNotEmpty ? '$label，$sublabel' : label;

    return Semantics(
      label: semanticsText,
      button: true,
      child: GestureDetector(
        // 非 TalkBack：手指按下播報標籤（防誤觸）
        onTapDown: (!isTalkBackOn && onAnnounce != null)
            ? (_) {
                HapticFeedback.lightImpact();
                onAnnounce!(semanticsText);
              }
            : null,
        // 手指離開 → 執行動作
        onTap: () {
          HapticFeedback.heavyImpact();
          onAction();
        },
        child: Container(
          color: color,
          constraints: const BoxConstraints(minHeight: 100),
          padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                label,
                style: const TextStyle(
                  fontSize: 32,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              if (sublabel.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(
                    sublabel,
                    style: const TextStyle(
                      fontSize: 20,
                      color: Colors.white70,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
