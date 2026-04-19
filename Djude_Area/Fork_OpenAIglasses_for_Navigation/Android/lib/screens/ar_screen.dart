// lib/screens/ar_screen.dart
// AR 偵測畫面：顯示伺服器 YOLO 處理後的即時 JPEG 幀
// DEBUG 面板由外層 OverlayEntry 的 DebugFloatingPanel 提供

import 'dart:async';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';

class ArScreen extends StatefulWidget {
  final String title;
  const ArScreen({super.key, required this.title});

  @override
  State<ArScreen> createState() => _ArScreenState();
}

class _ArScreenState extends State<ArScreen> {
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
    super.dispose();
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
      body: Column(
        children: [
          // AppBar 手動實作
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
                  // FPS 顯示
                  const SizedBox(width: 8),
                  Text('$_fps fps',
                      style: const TextStyle(
                          color: Colors.white38, fontSize: 12)),
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
      ), // Scaffold
    );   // GestureDetector
  }
}

