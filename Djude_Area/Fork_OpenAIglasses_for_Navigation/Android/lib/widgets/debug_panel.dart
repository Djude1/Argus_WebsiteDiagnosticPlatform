// lib/widgets/debug_panel.dart
// 開發者 DEBUG 浮動面板
//   • 平時：右側邊緣顯示一條小 tab（半透明）
//   • 向左滑 tab / 點擊 tab → 面板從右滑入展開
//   • 向右滑面板 → 收起
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
    return Consumer<AppProvider>(
      builder: (_, app, __) {
        // 訊息更新時捲到底
        if (_open) _scrollToBottom();

        final panelW = MediaQuery.of(context).size.width * 0.78;

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

            // ── 收合時的 tab 把手 ─────────────────────────────────────
            if (!_open || _animCtrl.isAnimating)
              Positioned(
                right:  0,
                top:    MediaQuery.of(context).size.height * 0.30,
                child: GestureDetector(
                  onTap: _open_,
                  // 向左滑動（負速度）展開
                  onHorizontalDragEnd: (d) {
                    if ((d.primaryVelocity ?? 0) < -150) _open_();
                  },
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    width:  28,
                    height: 80,
                    decoration: BoxDecoration(
                      color: const Color(0xFFFFB300).withAlpha(210),
                      borderRadius: const BorderRadius.horizontal(
                          left: Radius.circular(10)),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withAlpha(80),
                          blurRadius: 6,
                          offset: const Offset(-2, 0),
                        ),
                      ],
                    ),
                    child: const Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.bug_report,
                            size: 18, color: Colors.black87),
                        SizedBox(height: 4),
                        RotatedBox(
                          quarterTurns: 1,
                          child: Text('DEBUG',
                              style: TextStyle(
                                  fontSize: 8,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.black87,
                                  letterSpacing: 0.5)),
                        ),
                      ],
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

            // ── 面板可捲動區域 ───────────────────────────────────────
            Expanded(
              child: ListView(
                controller: widget.scrollCtrl,
                padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
                children: [

                  // ── APP 本機狀態 ─────────────────────────────────
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
              ),
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
