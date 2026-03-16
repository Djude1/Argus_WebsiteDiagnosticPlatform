// lib/screens/ar_screen.dart
// AR 偵測畫面：顯示伺服器 YOLO 處理後的即時 JPEG 幀，供 DEBUG 用

import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';

class ArScreen extends StatefulWidget {
  /// 顯示在頂部的功能名稱（例如「盲道導航」）
  final String title;

  const ArScreen({super.key, required this.title});

  @override
  State<ArScreen> createState() => _ArScreenState();
}

class _ArScreenState extends State<ArScreen> {
  Uint8List? _frame;

  @override
  void initState() {
    super.initState();
    context.read<AppProvider>().startViewer();
  }

  @override
  void dispose() {
    context.read<AppProvider>().stopViewer();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final app = context.read<AppProvider>();

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black87,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          tooltip: '返回',
          onPressed: () => Navigator.pop(context),
        ),
        title: Text(
          widget.title,
          style: const TextStyle(color: Colors.white, fontSize: 18),
        ),
        actions: [
          // 右上角顯示目前導航狀態
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
            child: StreamBuilder<void>(
              stream: Stream.periodic(const Duration(seconds: 1)),
              builder: (_, __) => Text(
                app.navStateLabel,
                style: const TextStyle(color: Colors.greenAccent, fontSize: 14),
              ),
            ),
          ),
        ],
      ),
      body: StreamBuilder<Uint8List>(
        stream: app.viewerStream,
        builder: (context, snapshot) {
          // 尚未收到第一幀
          if (!snapshot.hasData) {
            return const Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(color: Colors.white54),
                  SizedBox(height: 16),
                  Text(
                    '等待 YOLO 影像串流…',
                    style: TextStyle(color: Colors.white54, fontSize: 16),
                  ),
                  SizedBox(height: 8),
                  Text(
                    '確認伺服器已收到相機畫面',
                    style: TextStyle(color: Colors.white30, fontSize: 13),
                  ),
                ],
              ),
            );
          }

          // 顯示 JPEG 幀（填滿螢幕，保持比例）
          return Center(
            child: Image.memory(
              snapshot.data!,
              gaplessPlayback: true, // 避免幀切換時閃爍
              fit: BoxFit.contain,
              width:  double.infinity,
              height: double.infinity,
            ),
          );
        },
      ),
    );
  }
}
