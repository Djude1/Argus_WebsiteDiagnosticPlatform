// lib/widgets/debug_panel.dart
// 開發者 DEBUG 懸浮球（iOS AssistiveTouch 風格）
//   • 平時：半透明圓球，可自由拖曳到螢幕任意位置
//   • 點擊圓球 → 面板從右滑入展開
//   • 點擊關閉 / 向右滑 → 收起面板，圓球自動吸附至最近邊緣
//   • 透過 OverlayEntry 插入，跨所有子頁面持續顯示

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';
import '../core/constants.dart';

class DebugFloatingPanel extends StatefulWidget {
  const DebugFloatingPanel({super.key});

  @override
  State<DebugFloatingPanel> createState() => _DebugFloatingPanelState();
}

class _DebugFloatingPanelState extends State<DebugFloatingPanel>
    with SingleTickerProviderStateMixin {
  bool _open = false;
  late AnimationController _animCtrl;
  late Animation<Offset>   _slideAnim;
  final _scrollCtrl = ScrollController();

  // ── 拖曳位置 ───────────────────────────────────────────────────────────
  static const _ballSize = 44.0;
  double _dx = -1;   // 初始化標記（-1 表示尚未初始化）
  double _dy = -1;
  bool _dragging = false;

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 280),
    );
    _slideAnim = Tween<Offset>(
      begin: const Offset(1.0, 0),
      end:   Offset.zero,
    ).animate(CurvedAnimation(parent: _animCtrl, curve: Curves.easeOut));
  }

  @override
  void dispose() {
    _animCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  void _open_()  { setState(() => _open = true);  _animCtrl.forward(); }
  void _close_() { setState(() => _open = false); _animCtrl.reverse(); }

  /// 圓球吸附到最近的左/右邊緣
  void _snapToEdge(Size screenSize) {
    final centerX = _dx + _ballSize / 2;
    final margin = 4.0;
    setState(() {
      _dx = centerX < screenSize.width / 2
          ? margin
          : screenSize.width - _ballSize - margin;
      // 上下邊界限制
      _dy = _dy.clamp(
        MediaQuery.of(context).padding.top + margin,
        screenSize.height - _ballSize - margin,
      );
    });
  }

  // 自動捲到最新訊息
  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 150),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final screenSize = MediaQuery.of(context).size;

    // 首次初始化位置：右邊緣中間偏上
    if (_dx < 0) {
      _dx = screenSize.width - _ballSize - 4;
      _dy = screenSize.height * 0.30;
    }

    return Consumer<AppProvider>(
      builder: (_, app, __) {
        if (_open) _scrollToBottom();

        final panelW = screenSize.width * 0.78;

        return Stack(
          children: [

            // ── 背景遮罩（展開時，點擊關閉）──────────────────────────
            if (_open)
              Positioned.fill(
                child: GestureDetector(
                  onTap: _close_,
                  behavior: HitTestBehavior.opaque,
                  child: Container(color: Colors.black.withAlpha(80)),
                ),
              ),

            // ── 懸浮圓球（可拖曳，收合時顯示）───────────────────────
            if (!_open)
              Positioned(
                left: _dx,
                top:  _dy,
                child: GestureDetector(
                  onTap: _open_,
                  onPanStart: (_) => _dragging = true,
                  onPanUpdate: (d) {
                    setState(() {
                      _dx += d.delta.dx;
                      _dy += d.delta.dy;
                    });
                  },
                  onPanEnd: (_) {
                    _dragging = false;
                    _snapToEdge(screenSize);
                  },
                  child: AnimatedOpacity(
                    opacity: _dragging ? 1.0 : 0.65,
                    duration: const Duration(milliseconds: 200),
                    child: Container(
                      width:  _ballSize,
                      height: _ballSize,
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFB300),
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withAlpha(100),
                            blurRadius: 8,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: const Icon(Icons.bug_report,
                          size: 22, color: Colors.black87),
                    ),
                  ),
                ),
              ),

            // ── 展開面板（從右側滑入）────────────────────────────────
            if (_open || _animCtrl.isAnimating)
              Positioned(
                right: 0, top: 0, bottom: 0,
                width: panelW,
                child: SlideTransition(
                  position: _slideAnim,
                  child: GestureDetector(
                    // 向右滑收起
                    onHorizontalDragEnd: (d) {
                      if ((d.primaryVelocity ?? 0) > 200) _close_();
                    },
                    child: _PanelContent(
                      app:        app,
                      scrollCtrl: _scrollCtrl,
                      onClose:    _close_,
                    ),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}

// ── 面板內容（StatefulWidget：支援定時輪詢伺服器 Debug 狀態）────────────────
class _PanelContent extends StatefulWidget {
  final AppProvider    app;
  final ScrollController scrollCtrl;
  final VoidCallback   onClose;

  const _PanelContent({
    required this.app,
    required this.scrollCtrl,
    required this.onClose,
  });

  @override
  State<_PanelContent> createState() => _PanelContentState();
}

class _PanelContentState extends State<_PanelContent> {
  Map<String, dynamic>? _serverDebug;
  String? _fetchError;
  bool _fetching = false;
  int _currentTab = 0; // 0=總覽, 1=ASR 語音

  // ── ASR 狀態顏色 ────────────────────────────────────────────────────────
  Color _asrStateColor(String state) {
    switch (state) {
      case 'listening':  return Colors.greenAccent;
      case 'processing': return Colors.orangeAccent;
      case 'standby':    return Colors.white38;
      default:           return Colors.white38;
    }
  }

  String _asrStateLabel(String state) {
    switch (state) {
      case 'listening':  return '聆聽中';
      case 'processing': return '處理中';
      case 'standby':    return '待機';
      default:           return state;
    }
  }

  @override
  void initState() {
    super.initState();
    _fetchDebugStatus();
    // 每 3 秒輪詢一次伺服器 debug 狀態
    _startPolling();
  }

  // 定時輪詢（面板展開時才會存在，收起時 State 被銷毀 → 自動停止）
  void _startPolling() {
    Future.doWhile(() async {
      await Future.delayed(const Duration(seconds: 3));
      if (!mounted) return false;
      await _fetchDebugStatus();
      return mounted;
    });
  }

  Future<void> _fetchDebugStatus() async {
    if (_fetching || !mounted) return;
    // 未連線時不嘗試拉取，避免不必要的錯誤
    if (!widget.app.connected) {
      if (mounted) setState(() { _fetchError = '尚未連線伺服器'; _serverDebug = null; });
      return;
    }
    _fetching = true;
    try {
      final data = await widget.app.api.debugStatus();
      if (mounted) setState(() { _serverDebug = data; _fetchError = null; });
    } catch (e) {
      if (mounted) setState(() { _fetchError = e.toString(); });
    } finally {
      _fetching = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = widget.app;
    final serverUrl = app.baseUrl.isNotEmpty
        ? app.baseUrl
        : '${app.host}:${app.port}';
    final d = _serverDebug;

    return Container(
      color: Colors.black.withAlpha(245),
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [

            // ── 標題列 ─────────────────────────────────────────────
            Container(
              color: const Color(0xFFFFB300),
              padding: const EdgeInsets.symmetric(
                  vertical: 10, horizontal: 14),
              child: Row(
                children: [
                  const Icon(Icons.bug_report,
                      size: 18, color: Colors.black),
                  const SizedBox(width: 8),
                  const Expanded(
                    child: Text('DEBUG',
                        style: TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.bold,
                            color: Colors.black)),
                  ),
                  const Text('← 右滑收起',
                      style: TextStyle(
                          fontSize: 10, color: Colors.black54)),
                  const SizedBox(width: 8),
                  GestureDetector(
                    onTap: widget.onClose,
                    child: const Icon(Icons.close,
                        size: 20, color: Colors.black87),
                  ),
                ],
              ),
            ),

            // ── 分頁切換列 ─────────────────────────────────────────
            Container(
              color: Colors.white.withAlpha(15),
              child: Row(
                children: [
                  _TabButton(
                    label: '總覽',
                    selected: _currentTab == 0,
                    onTap: () => setState(() => _currentTab = 0),
                  ),
                  _TabButton(
                    label: 'ASR 語音',
                    selected: _currentTab == 1,
                    onTap: () => setState(() => _currentTab = 1),
                  ),
                ],
              ),
            ),

            // ── 面板可捲動區域（依分頁切換）──────────────────────────
            Expanded(
              child: _currentTab == 0
                  ? _buildOverviewTab(app, serverUrl, d)
                  : _buildAsrTab(app, d),
            ),

            // ── API 端點 ───────────────────────────────────────────
            Container(
              color: Colors.white.withAlpha(8),
              padding: const EdgeInsets.all(8),
              child: Text(
                'API: ${AppConstants.httpBase(app.host, app.port, secure: app.secure, baseUrl: app.baseUrl.isNotEmpty ? app.baseUrl : null)}',
                style: const TextStyle(
                    fontSize: 9, color: Colors.white30),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ── 總覽分頁 ────────────────────────────────────────────────────────────
  Widget _buildOverviewTab(AppProvider app, String serverUrl, Map<String, dynamic>? d) {
    return ListView(
      controller: widget.scrollCtrl,
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      children: [

        // ── APP 本機狀態 ─────────────────────────────────────────
        _SectionTitle('APP 本機狀態'),
        _Row('伺服器',   serverUrl,
            color: app.connected
                ? Colors.greenAccent : Colors.redAccent),
        _Row('連線',     app.connected ? '已連線' : '未連線',
            color: app.connected
                ? Colors.greenAccent : Colors.redAccent),
        _Row('導航狀態', '${app.navState}（${app.navStateLabel}）'),
        _Row('麥克風',
            app.isRecordingMic ? '錄音中' : '未啟動',
            color: app.isRecordingMic
                ? Colors.greenAccent : Colors.white38),
        _Row('TTS',
            app.ttsEnabled ? '已開啟' : '已關閉',
            color: app.ttsEnabled
                ? Colors.greenAccent : Colors.white38),
        const SizedBox(height: 8),
        const Divider(color: Colors.white12, height: 1),

        // ── 伺服器 Debug 狀態 ────────────────────────────
        const SizedBox(height: 8),
        _SectionTitle('伺服器 Debug 狀態'),

        if (_fetchError != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Text('拉取失敗：$_fetchError',
                style: const TextStyle(
                    fontSize: 10, color: Colors.redAccent)),
          )
        else if (d == null)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 4),
            child: Text('載入中…',
                style: TextStyle(
                    fontSize: 10, color: Colors.white30)),
          )
        else ...[
          // 連線
          _SubTitle('連線狀態'),
          _Row('攝影機 WS',
              d['esp32_camera_connected'] == true ? '已連線' : '未連線',
              color: d['esp32_camera_connected'] == true
                  ? Colors.greenAccent : Colors.redAccent),
          _Row('音訊 WS',
              d['esp32_audio_connected'] == true ? '已連線' : '未連線',
              color: d['esp32_audio_connected'] == true
                  ? Colors.greenAccent : Colors.redAccent),
          _Row('UI 客戶端',  '${d['ui_client_count']}'),
          _Row('觀看者',    '${d['camera_viewer_count']}'),
          _Row('IMU 客戶端', '${d['imu_ws_client_count']}'),

          // 導航
          _SubTitle('導航狀態'),
          _Row('狀態機',   '${d['orchestrator_state']}'),
          _Row('盲道導航',
              d['navigation_active'] == true ? '啟用中' : '未啟用',
              color: d['navigation_active'] == true
                  ? Colors.greenAccent : Colors.white38),
          _Row('過馬路',
              d['cross_street_active'] == true ? '啟用中' : '未啟用',
              color: d['cross_street_active'] == true
                  ? Colors.greenAccent : Colors.white38),

          // 模型
          _SubTitle('模型狀態'),
          _Row('YOLO 分割',
              d['yolo_seg_loaded'] == true ? '已載入' : '未載入',
              color: d['yolo_seg_loaded'] == true
                  ? Colors.greenAccent : Colors.redAccent),
          _Row('障礙物偵測',
              d['obstacle_detector_loaded'] == true ? '已載入' : '未載入',
              color: d['obstacle_detector_loaded'] == true
                  ? Colors.greenAccent : Colors.redAccent),
          _Row('GPU',
              d['gpu_available'] == true
                  ? '${d['gpu_name']}'
                  : '不可用 (CPU)',
              color: d['gpu_available'] == true
                  ? Colors.greenAccent : Colors.amber),

          // ASR
          _SubTitle('ASR 語音辨識'),
          _Row('Partial',    '${d['current_partial_len']} 字'),
          _Row('Final 紀錄', '${d['recent_finals_count']} 筆'),
          if ((d['last_final'] ?? '').toString().isNotEmpty)
            _Row('最新辨識',  '${d['last_final']}'),

          // 音訊
          _SubTitle('音訊狀態'),
          _Row('Debug 錄音',
              d['debug_rec_active'] == true ? '錄音中' : '閒置',
              color: d['debug_rec_active'] == true
                  ? Colors.amber : Colors.white38),
          if (d['debug_rec_active'] == true)
            _Row('錄音緩衝',
                '${(d['debug_rec_bytes'] / 1024).toStringAsFixed(1)} KB'),
          _Row('聲紋錄製',
              d['enroll_active'] == true ? '錄製中' : '閒置'),
          _Row('持續監測',
              d['verify_continuous'] == true ? '監測中' : '關閉'),
          _Row('取樣率',    '${d['sample_rate']} Hz'),

          // 系統
          _SubTitle('系統資訊'),
          _Row('運行時間',  '${d['uptime']}'),
        ],

        const SizedBox(height: 8),
        const Divider(color: Colors.white12, height: 1),

        // ── 訊息記錄標題 ─────────────────────────────────
        const SizedBox(height: 8),
        Row(
          children: [
            _SectionTitle('訊息記錄'),
            const Spacer(),
            Text('${app.messages.length} 筆',
                style: const TextStyle(
                    fontSize: 10, color: Colors.white30)),
          ],
        ),

        // ── 訊息清單 ─────────────────────────────────────
        ...app.messages.map((msg) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 1.5),
          child: Text(
            msg,
            style: TextStyle(
              fontSize:   10.5,
              color:      _msgColor(msg),
              fontFamily: 'monospace',
            ),
          ),
        )),
      ],
    );
  }

  // ── ASR 語音分頁 ────────────────────────────────────────────────────────
  Widget _buildAsrTab(AppProvider app, Map<String, dynamic>? d) {
    final asrState = app.asrState;
    final partialText = app.asrPartialText;
    final finals = app.asrFinals;

    return ListView(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      children: [
        // ── ASR 狀態指示 ─────────────────────────────────
        _SectionTitle('ASR 收音狀態'),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: _asrStateColor(asrState).withAlpha(25),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: _asrStateColor(asrState).withAlpha(80)),
          ),
          child: Row(
            children: [
              // 狀態指示燈
              Container(
                width: 12, height: 12,
                decoration: BoxDecoration(
                  color: _asrStateColor(asrState),
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 10),
              Text(
                _asrStateLabel(asrState),
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                  color: _asrStateColor(asrState),
                ),
              ),
              const Spacer(),
              Text(
                app.isRecordingMic ? '麥克風錄音中' : '麥克風未啟動',
                style: TextStyle(
                  fontSize: 10,
                  color: app.isRecordingMic ? Colors.greenAccent : Colors.white38,
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 16),

        // ── 即時辨識（Partial）─────────────────────────────
        _SectionTitle('即時辨識'),
        Container(
          width: double.infinity,
          constraints: const BoxConstraints(minHeight: 48),
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: Colors.white.withAlpha(8),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: Colors.white12),
          ),
          child: Text(
            partialText.isEmpty ? '（等待語音輸入…）' : partialText,
            style: TextStyle(
              fontSize: 13,
              color: partialText.isEmpty ? Colors.white24 : Colors.cyanAccent,
              fontFamily: 'monospace',
            ),
          ),
        ),

        const SizedBox(height: 16),

        // ── 伺服器 ASR 狀態（來自 debug API）───────────────
        if (d != null) ...[
          _SectionTitle('伺服器 ASR'),
          _Row('Partial', '${d['current_partial_len']} 字'),
          _Row('Final 紀錄', '${d['recent_finals_count']} 筆'),
          if ((d['last_final'] ?? '').toString().isNotEmpty)
            _Row('最新辨識', '${d['last_final']}'),
          const SizedBox(height: 16),
        ],

        // ── 辨識歷史（Finals）──────────────────────────────
        Row(
          children: [
            _SectionTitle('辨識歷史'),
            const Spacer(),
            Text('${finals.length} 筆',
                style: const TextStyle(fontSize: 10, color: Colors.white30)),
          ],
        ),

        if (finals.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Text('尚無辨識紀錄',
                style: TextStyle(fontSize: 11, color: Colors.white24)),
          )
        else
          ...finals.reversed.map((text) => Container(
            width: double.infinity,
            margin: const EdgeInsets.only(bottom: 4),
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            decoration: BoxDecoration(
              color: Colors.white.withAlpha(6),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              text,
              style: const TextStyle(
                fontSize: 10.5,
                color: Colors.white70,
                fontFamily: 'monospace',
              ),
            ),
          )),
      ],
    );
  }

  Color _msgColor(String msg) {
    if (msg.contains('[錯誤]')) return Colors.redAccent;
    if (msg.contains('[ASR]') || msg.contains('[USER]')) {
      return Colors.cyanAccent;
    }
    if (msg.contains('[系統]')) return Colors.white70;
    if (msg.contains('[狀態]')) return Colors.greenAccent;
    return Colors.white38;
  }
}

// ── 狀態資訊列 ────────────────────────────────────────────────────────────────
class _Row extends StatelessWidget {
  final String label;
  final String value;
  final Color? color;

  const _Row(this.label, this.value, {this.color});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2.5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 78,
            child: Text(label,
                style: const TextStyle(
                    fontSize: 10,
                    color: Colors.white38,
                    fontFamily: 'monospace')),
          ),
          Expanded(
            child: Text(
              value,
              style: TextStyle(
                  fontSize: 10,
                  color: color ?? Colors.white70,
                  fontFamily: 'monospace'),
            ),
          ),
        ],
      ),
    );
  }
}

// ── 區段標題 ──────────────────────────────────────────────────────────────────
class _SectionTitle extends StatelessWidget {
  final String text;
  const _SectionTitle(this.text);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4, bottom: 6),
      child: Text(text,
          style: const TextStyle(
              fontSize: 11,
              color: Colors.amber,
              fontWeight: FontWeight.bold,
              letterSpacing: 1)),
    );
  }
}

// ── 子區段標題 ────────────────────────────────────────────────────────────────
class _SubTitle extends StatelessWidget {
  final String text;
  const _SubTitle(this.text);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 6, bottom: 2),
      child: Text(text,
          style: TextStyle(
              fontSize: 10,
              color: Colors.blueAccent.withAlpha(180),
              fontWeight: FontWeight.w600)),
    );
  }
}

// ── 分頁切換按鈕 ──────────────────────────────────────────────────────────────
class _TabButton extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _TabButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(
                color: selected ? const Color(0xFFFFB300) : Colors.transparent,
                width: 2.5,
              ),
            ),
          ),
          child: Text(
            label,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 12,
              fontWeight: selected ? FontWeight.bold : FontWeight.normal,
              color: selected ? const Color(0xFFFFB300) : Colors.white54,
            ),
          ),
        ),
      ),
    );
  }
}
