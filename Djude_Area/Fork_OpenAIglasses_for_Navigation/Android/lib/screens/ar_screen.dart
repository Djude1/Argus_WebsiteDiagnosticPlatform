// lib/screens/ar_screen.dart
// AR 偵測畫面：顯示伺服器 YOLO 處理後的即時 JPEG 幀
// 右上角小蟲圖示 → 點開 DEBUG 面板（隱藏選單）

import 'dart:async';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';
import '../core/constants.dart';

class ArScreen extends StatefulWidget {
  final String title;
  const ArScreen({super.key, required this.title});

  @override
  State<ArScreen> createState() => _ArScreenState();
}

class _ArScreenState extends State<ArScreen>
    with SingleTickerProviderStateMixin {
  bool _debugOpen = false;
  late AnimationController _animCtrl;
  late Animation<Offset> _slideAnim;

  // 串流幀率計算（獨立 subscription，不在 builder 裡 setState）
  StreamSubscription<Uint8List>? _fpsSub;
  int _frameCount   = 0;
  int _fps          = 0;
  DateTime _lastFpsTime = DateTime.now();

  @override
  void initState() {
    super.initState();
    final app = context.read<AppProvider>();
    app.startViewer();

    _animCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 280),
    );
    _slideAnim = Tween<Offset>(
      begin: const Offset(1, 0),
      end:   Offset.zero,
    ).animate(CurvedAnimation(parent: _animCtrl, curve: Curves.easeOut));

    // 獨立監聽 viewer stream 計算 FPS（不干擾 StreamBuilder 的 build）
    _fpsSub = app.viewerStream.listen((_) {
      _frameCount++;
      final now     = DateTime.now();
      final elapsed = now.difference(_lastFpsTime).inMilliseconds;
      if (elapsed >= 1000 && mounted) {
        setState(() {
          _fps          = (_frameCount * 1000 / elapsed).round();
          _frameCount   = 0;
          _lastFpsTime  = now;
        });
      }
    });
  }

  @override
  void dispose() {
    _fpsSub?.cancel();
    context.read<AppProvider>().stopViewer();
    _animCtrl.dispose();
    super.dispose();
  }

  void _toggleDebug() {
    setState(() => _debugOpen = !_debugOpen);
    if (_debugOpen) {
      _animCtrl.forward();
    } else {
      _animCtrl.reverse();
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppProvider>();

    return GestureDetector(
      onHorizontalDragEnd: (d) {
        if ((d.primaryVelocity ?? 0) > 300) Navigator.pop(context);
      },
      child: Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        children: [
          // ── AR 畫面主體 ──────────────────────────────────────────────────
          Column(
            children: [
              // AppBar 手動實作（讓 Stack 能覆蓋全螢幕）
              SafeArea(
                bottom: false,
                child: Container(
                  color: Colors.black87,
                  padding: const EdgeInsets.symmetric(
                      horizontal: 4, vertical: 6),
                  child: Row(
                    children: [
                      Text(widget.title,
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 18,
                              fontWeight: FontWeight.bold)),
                      const Spacer(),
                      // 導航狀態標籤
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: Colors.greenAccent.withAlpha(30),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          app.navStateLabel,
                          style: const TextStyle(
                              color: Colors.greenAccent, fontSize: 13),
                        ),
                      ),
                      const SizedBox(width: 8),
                      // Debug 按鈕（小蟲）
                      Tooltip(
                        message: 'DEBUG',
                        child: GestureDetector(
                          onTap: _toggleDebug,
                          child: Container(
                            width: 36, height: 36,
                            decoration: BoxDecoration(
                              color: _debugOpen
                                  ? Colors.amber.withAlpha(200)
                                  : Colors.white12,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Icon(
                              Icons.bug_report,
                              size: 20,
                              color: _debugOpen
                                  ? Colors.black
                                  : Colors.white54,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                    ],
                  ),
                ),
              ),

              // YOLO 影像
              Expanded(
                child: StreamBuilder<Uint8List>(
                  stream: app.viewerStream,
                  builder: (context, snapshot) {
                    if (!snapshot.hasData) {
                      return const Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            CircularProgressIndicator(
                                color: Colors.white54),
                            SizedBox(height: 16),
                            Text('等待 YOLO 影像串流…',
                                style: TextStyle(
                                    color: Colors.white54, fontSize: 16)),
                            SizedBox(height: 8),
                            Text('確認伺服器已收到相機畫面',
                                style: TextStyle(
                                    color: Colors.white30, fontSize: 13)),
                          ],
                        ),
                      );
                    }
                    return Center(
                      child: Image.memory(
                        snapshot.data!,
                        gaplessPlayback: true,
                        fit: BoxFit.contain,
                        width:  double.infinity,
                        height: double.infinity,
                      ),
                    );
                  },
                ),
              ),
            ],
          ),

          // ── DEBUG 面板（右側滑入）──────────────────────────────────────────
          if (_debugOpen || _animCtrl.isAnimating)
            Positioned(
              top: 0, bottom: 0, right: 0,
              width: MediaQuery.of(context).size.width * 0.72,
              child: SlideTransition(
                position: _slideAnim,
                child: _DebugPanel(app: app, fps: _fps, onClose: _toggleDebug),
              ),
            ),
        ],
      ),
      ), // Scaffold
    );   // GestureDetector
  }
}

// ════════════════════════════════════════════════════════════════════════════
// Debug 面板內容
// ════════════════════════════════════════════════════════════════════════════
class _DebugPanel extends StatelessWidget {
  final AppProvider app;
  final int fps;
  final VoidCallback onClose;

  const _DebugPanel({required this.app, required this.fps, required this.onClose});

  @override
  Widget build(BuildContext context) {
    final serverUrl = app.baseUrl.isNotEmpty
        ? app.baseUrl
        : '${app.host}:${app.port}';

    return Container(
      color: Colors.black.withAlpha(230),
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ── 標題 ──────────────────────────────────────────────────────
            Container(
              color: Colors.amber.withAlpha(200),
              padding: const EdgeInsets.symmetric(
                  vertical: 10, horizontal: 14),
              child: Row(
                children: [
                  const Icon(Icons.bug_report, size: 18, color: Colors.black),
                  const SizedBox(width: 8),
                  const Expanded(
                    child: Text('DEBUG',
                        style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            color: Colors.black)),
                  ),
                  // 關閉按鈕
                  GestureDetector(
                    onTap: onClose,
                    child: const Icon(Icons.close, size: 20, color: Colors.black87),
                  ),
                ],
              ),
            ),

            // ── 系統資訊 ──────────────────────────────────────────────────
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _DebugRow('伺服器', serverUrl,
                      color: app.connected
                          ? Colors.greenAccent
                          : Colors.redAccent),
                  _DebugRow('連線狀態',
                      app.connected ? '已連線 ✓' : '未連線 ✗',
                      color: app.connected
                          ? Colors.greenAccent
                          : Colors.redAccent),
                  _DebugRow('導航狀態', app.navState),
                  _DebugRow('狀態標籤', app.navStateLabel),
                  _DebugRow('串流 FPS', '$fps fps'),
                ],
              ),
            ),

            const Divider(color: Colors.white12, height: 1),

            // ── 最新訊息 ──────────────────────────────────────────────────
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 4),
              child: const Text('最新訊息',
                  style: TextStyle(
                      fontSize: 12,
                      color: Colors.amber,
                      fontWeight: FontWeight.bold)),
            ),
            Expanded(
              child: ListView.builder(
                padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                // 反向顯示（最新在最上面）
                reverse: true,
                itemCount: app.messages.length,
                itemBuilder: (_, i) {
                  // 從最新到最舊
                  final msg = app.messages[
                      app.messages.length - 1 - i];
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Text(
                      msg,
                      style: TextStyle(
                        fontSize: 11,
                        color: _msgColor(msg),
                        fontFamily: 'monospace',
                      ),
                    ),
                  );
                },
              ),
            ),

            // ── API 端點 ──────────────────────────────────────────────────
            Container(
              color: Colors.white.withAlpha(10),
              padding: const EdgeInsets.all(10),
              child: Text(
                'API: ${AppConstants.httpBase(app.host, app.port, secure: app.secure, baseUrl: app.baseUrl.isNotEmpty ? app.baseUrl : null)}',
                style: const TextStyle(
                    fontSize: 10, color: Colors.white38),
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
    return Colors.white54;
  }
}

class _DebugRow extends StatelessWidget {
  final String label;
  final String value;
  final Color? color;

  const _DebugRow(this.label, this.value, {this.color});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 80,
            child: Text(label,
                style: const TextStyle(
                    fontSize: 11,
                    color: Colors.white38,
                    fontFamily: 'monospace')),
          ),
          Expanded(
            child: Text(
              value,
              style: TextStyle(
                  fontSize: 11,
                  color: color ?? Colors.white,
                  fontFamily: 'monospace'),
            ),
          ),
        ],
      ),
    );
  }
}
