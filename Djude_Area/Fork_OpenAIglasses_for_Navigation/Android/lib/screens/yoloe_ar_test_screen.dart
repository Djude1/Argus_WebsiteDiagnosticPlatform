// lib/screens/yoloe_ar_test_screen.dart
// 開發者工具：yoloe-26n-seg AR 測試頁
// 對應計畫：MD/plan_mobile_yolo_deployment.md Phase A.4
//
// 本檔目前為 UI 骨架（全螢幕相機 + AR 疊加 + 場景切換 + mock 偵測）。
// ONNX Runtime 推論整合屬計畫 Phase 3.1（Week 3 工作），於本檔以 TODO 標示。

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';

import '../core/yoloe_label_zh.dart';
import '../providers/app_provider.dart';
import '../services/yoloe_inference.dart';
import '../utils/hardware_monitor.dart';

// ── 偵測結果結構 ─────────────────────────────────────────────────────
// 避障專用：近/遠距離判斷直接仿 obstacle_detector_client.detect 吐出的
// area_ratio / bottom_y_ratio（規則同 workflow_blindpath._add_obstacle_
// visualization：bottom_y_ratio > 0.7 或 area_ratio > 0.1 視為近距離）。
class Detection {
  final String label;             // 英文類別（用於對照 kYoloeLabelZh）
  final double confidence;        // 0~1
  final Rect box;                 // portrait 直立座標系（旋轉 90° CW 後）
  final List<Offset>? polygon;    // segmentation 外輪廓（跟 box 同座標系）。
                                  // 仿 _add_obstacle_visualization：mask 二值化
                                  // → 最大 contour → 抽樣 → polygon points，
                                  // painter 只描邊、不填色。
  final double areaRatio;         // mask 前景占整幅面積比，> 0.1 視為近
  final double bottomYRatio;      // portrait 底邊高度比，> 0.7 視為近

  const Detection({
    required this.label,
    required this.confidence,
    required this.box,
    this.polygon,
    this.areaRatio = 0.0,
    this.bottomYRatio = 0.0,
  });

  /// 近距離判斷（仿 _add_obstacle_visualization:2361）
  bool get isNear => bottomYRatio > 0.7 || areaRatio > 0.1;
}

/// 單次推論回傳：含偵測 + 推論當下 CameraImage 的真實尺寸。
/// painter 必須用 srcH/srcW 對齊（而非 previewSize），因為某些裝置
/// previewSize ≠ CameraImage.width/height。
class InferResult {
  final List<Detection> detections;
  final int srcW;   // CameraImage.width  (sensor 橫向)
  final int srcH;   // CameraImage.height
  final double globalMaxConf;   // 本幀 output0 最高分數（診斷用）
  const InferResult({
    required this.detections,
    required this.srcW,
    required this.srcH,
    this.globalMaxConf = 0.0,
  });
}

// ── 主頁面 ───────────────────────────────────────────────────────────
class YoloeArTestScreen extends StatefulWidget {
  const YoloeArTestScreen({super.key});

  @override
  State<YoloeArTestScreen> createState() => _YoloeArTestScreenState();
}

class _YoloeArTestScreenState extends State<YoloeArTestScreen>
    with WidgetsBindingObserver {
  CameraController? _camera;
  bool _cameraReady = false;
  String? _initError;

  double _confThreshold = 0.15;   // YOLOE 分數偏低，0.25 過嚴改為 0.15
  InferResult? _result;
  String? _inferError;            // init 失敗時的錯誤訊息
  bool _showLabels = false;       // 切換標籤清單面板

  // FPS 計數：在 startImageStream 的每幀回呼中累加 _frameCount，
  // 每超過 1 秒就把 frameCount/elapsed 換算成 fps 並 setState。
  int _fps = 0;
  int _frameCount = 0;
  int _fpsLastTickMs = 0;
  bool _streaming = false;

  // 效能監控
  final HardwareMonitor _hw = HardwareMonitor();

  // AppProvider 參考（initState 取得，dispose 時恢復主相機）
  late AppProvider _app;

  // 推論管線（單例，App 生命週期內共用）
  final YoloeInference _infer = YoloeInference();
  bool _inferReady = false;
  // 推論節流：onnxruntime Flutter 套件 value getter 把 native float buffer
  // 透過 dynamic List<num> 一個個 push，沒 zero-copy；output0 (1,4+nc+32,8400) +
  // proto1 (1,32,160,160) 主 isolate 一次攤平要 ~200ms。再加上 isolate 端
  // NMS + mask 解碼 + Moore tracing ~50ms，端到端 ~300ms。
  // 節流到 500ms（2 推論/秒）；相機畫面仍以原生 FPS 流暢顯示。
  int _lastInferAtMs = 0;
  static const int _inferIntervalMs = 500;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // 相機進入時鎖定為直立，避免 AR 疊加旋轉錯亂
    SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    _hw.start(() { if (mounted) setState(() {}); });
    // 暫停 AppProvider 的主相機串流，釋放 Camera2 session 給本頁使用。
    // 兩個 CameraController 同時持有同一鏡頭會導致 Camera2 session 搶奪，
    // 進而中斷主程式的 WebSocket 影像傳輸造成伺服器連線異常。
    _app = context.read<AppProvider>();
    _app.pauseCameraStreaming();
    _bootstrap();
    _initInference();
  }

  Future<void> _initInference() async {
    try {
      await _infer.init();
      if (mounted) setState(() { _inferReady = true; _inferError = null; });
    } catch (e) {
      debugPrint('[YoloeArTest] inference init failed: $e');
      if (mounted) setState(() => _inferError = e.toString());
    }
  }

  Future<void> _bootstrap() async {
    final ok = await Permission.camera.request();
    if (!ok.isGranted) {
      if (mounted) setState(() => _initError = '未取得相機權限');
      return;
    }
    try {
      final cams = await availableCameras();
      if (cams.isEmpty) {
        if (mounted) setState(() => _initError = '裝置無可用相機');
        return;
      }
      final back = cams.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cams.first,
      );
      final ctrl = CameraController(
        back,
        ResolutionPreset.medium,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.yuv420,
      );
      await ctrl.initialize();
      // 關閉閃光燈/補光燈，避免在低光環境自動點亮手電筒
      try {
        await ctrl.setFlashMode(FlashMode.off);
      } catch (_) {
        // 部分裝置不支援；忽略
      }
      if (!mounted) {
        await ctrl.dispose();
        return;
      }
      setState(() {
        _camera = ctrl;
        _cameraReady = true;
      });
      _startFpsStream(ctrl);
    } catch (e) {
      if (mounted) setState(() => _initError = '相機初始化失敗：$e');
    }
  }

  /// 啟動相機 image stream，僅用於累計 FPS。
  /// 未來 Phase 3.1 ONNX 整合時，可在同一個回呼裡把 [img] 餵給推論模型。
  void _startFpsStream(CameraController ctrl) {
    if (_streaming) return;
    _frameCount = 0;
    _fpsLastTickMs = DateTime.now().millisecondsSinceEpoch;
    try {
      ctrl.startImageStream((CameraImage img) {
        _frameCount++;
        final now = DateTime.now().millisecondsSinceEpoch;
        final elapsed = now - _fpsLastTickMs;
        if (elapsed >= 1000) {
          final fps = (_frameCount * 1000 / elapsed).round();
          _frameCount = 0;
          _fpsLastTickMs = now;
          if (mounted) setState(() => _fps = fps);
        }
        // 觸發推論：節流 + busy 雙保險
        if (_inferReady &&
            !_infer.isBusy &&
            now - _lastInferAtMs >= _inferIntervalMs) {
          _lastInferAtMs = now;
          _infer.confTh = _confThreshold;
          _infer.infer(img).then((res) {
            if (res != null && mounted) {
              setState(() => _result = res);
            }
          });
        }
      });
      _streaming = true;
    } catch (e) {
      // 部分裝置或模擬器可能不支援 image stream；FPS 維持 0
      debugPrint('[YoloeArTest] startImageStream 失敗：$e');
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final cam = _camera;
    if (cam == null || !cam.value.isInitialized) return;
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      _streaming = false;
      _cameraReady = false;
      _camera = null;
      cam.dispose();  // camera 套件內部處理殘留 stream
    } else if (state == AppLifecycleState.resumed) {
      _bootstrap();
    }
  }

  @override
  void dispose() {
    _hw.stop();
    _streaming = false;
    // 先取出 camera 引用再清空欄位，讓 build() 不再使用舊 controller
    final cam = _camera;
    _camera = null;
    _cameraReady = false;
    // 在 super.dispose() 之前釋放 camera，避免 deactivated 後觸發祖先查找
    // camera 套件的 dispose() 內部會自動停止殘留 image stream
    cam?.dispose();
    _infer.dispose();
    // 恢復 AppProvider 的主相機串流（離開 AR 測試頁）
    _app.resumeCameraStreaming();
    WidgetsBinding.instance.removeObserver(this);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    SystemChrome.setPreferredOrientations(DeviceOrientation.values);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_initError != null) {
      return _buildErrorScreen(_initError!);
    }
    if (!_cameraReady || _camera == null) {
      return const Scaffold(
        backgroundColor: Colors.black,
        body: Center(child: CircularProgressIndicator(color: Colors.white)),
      );
    }
    final preview = _camera!.value.previewSize!;
    // painter 偏好用 inference 回報的真實 srcSize（旋轉 90° CW 後的 portrait）；
    // 還沒推論過 → 退回 previewSize 轉置（兩者通常一致，但某些裝置會有差）。
    final res = _result;
    final Size imageSize = res != null && res.srcW > 0 && res.srcH > 0
        ? Size(res.srcH.toDouble(), res.srcW.toDouble())
        : Size(preview.height, preview.width);
    final detections = res?.detections ?? const <Detection>[];

    return Scaffold(
      backgroundColor: Colors.black,
      extendBodyBehindAppBar: true,
      extendBody: true,
      body: Stack(
        fit: StackFit.expand,
        children: [
          // 1. 相機預覽（全螢幕，覆滿）
          Positioned.fill(
            child: FittedBox(
              fit: BoxFit.cover,
              child: SizedBox(
                width: preview.height,
                height: preview.width,
                child: CameraPreview(_camera!),
              ),
            ),
          ),

          // 2. AR 偵測框疊加（polygon mask + box stroke + label）
          Positioned.fill(
            child: CustomPaint(
              painter: _DetectionPainter(
                detections: detections,
                imageSize: imageSize,
              ),
            ),
          ),

          // 3. 底部半透明控制列
          Positioned(
            left: 0, right: 0, bottom: 0,
            child: SafeArea(
              top: false,
              child: Container(
                margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: Colors.black.withAlpha(140),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // 第一列：避障模式徽章 + FPS + 偵測數
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            color: Colors.redAccent.withAlpha(25),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(
                                color: Colors.redAccent.withAlpha(100),
                                width: 0.8),
                          ),
                          child: const Text(
                            '避障模式',
                            style: TextStyle(
                              color: Colors.redAccent,
                              fontSize: 12,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                        const Spacer(),
                        _statBadge(Icons.videocam_outlined, '$_fps', 'FPS',
                            Colors.greenAccent),
                        const SizedBox(width: 6),
                        _statBadge(Icons.center_focus_weak, '${detections.length}',
                            '物', Colors.white70),
                        const SizedBox(width: 6),
                        _statBadge(
                          Icons.bar_chart,
                          (_result?.globalMaxConf ?? 0.0).toStringAsFixed(2),
                          'max',
                          (_result?.globalMaxConf ?? 0.0) > _confThreshold
                              ? Colors.yellowAccent
                              : Colors.grey,
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    // 第二列：效能監控
                    Row(
                      children: [
                        _hwChip(Icons.speed, '${_hw.cpuPercent}%', 'CPU',
                            _cpuColor(_hw.cpuPercent)),
                        const SizedBox(width: 6),
                        _hwChip(Icons.memory_outlined, '${_hw.appRamMB}MB', 'RAM',
                            Colors.purpleAccent),
                        const SizedBox(width: 6),
                        _hwChip(Icons.thermostat_outlined,
                            _hw.tempC >= 0 ? '${_hw.tempC}°C' : '-',
                            '溫度', _tempColor(_hw.tempC)),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        const Text('門檻',
                            style: TextStyle(color: Colors.white70, fontSize: 12)),
                        Expanded(
                          child: Slider(
                            value: _confThreshold,
                            min: 0.10, max: 0.90, divisions: 16,
                            activeColor: Colors.greenAccent,
                            inactiveColor: Colors.white24,
                            onChanged: (v) => setState(() => _confThreshold = v),
                          ),
                        ),
                        SizedBox(
                          width: 38,
                          child: Text(
                            _confThreshold.toStringAsFixed(2),
                            style: const TextStyle(color: Colors.white, fontSize: 12),
                            textAlign: TextAlign.right,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),

          // 4. 右上角返回按鈕
          Positioned(
            top: MediaQuery.of(context).padding.top + 4,
            right: 8,
            child: Material(
              color: Colors.black.withAlpha(120),
              shape: const CircleBorder(),
              child: IconButton(
                icon: const Icon(Icons.close, color: Colors.white, size: 26),
                tooltip: '返回',
                onPressed: () => Navigator.pop(context),
              ),
            ),
          ),

          // 5. 左上角：模型狀態 + 標籤清單按鈕
          Positioned(
            top: MediaQuery.of(context).padding.top + 6,
            left: 12,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 狀態徽章
                if (_inferError != null)
                  _statusBadge('⚠ 模型載入失敗', Colors.redAccent)
                else if (!_inferReady)
                  _statusBadge('模型載入中…', Colors.orange),

                const SizedBox(height: 4),

                // 標籤清單切換按鈕
                if (_inferReady)
                  GestureDetector(
                    onTap: () => setState(() => _showLabels = !_showLabels),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.black54,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Colors.white24),
                      ),
                      child: Text(
                        _showLabels ? '▲ 隱藏標籤' : '▼ ${_infer.labels.length} 個標籤',
                        style: const TextStyle(color: Colors.white70, fontSize: 11),
                      ),
                    ),
                  ),

                // 標籤清單面板
                if (_showLabels && _infer.labels.isNotEmpty)
                  Container(
                    margin: const EdgeInsets.only(top: 4),
                    padding: const EdgeInsets.all(8),
                    constraints: BoxConstraints(
                      maxHeight: MediaQuery.of(context).size.height * 0.4,
                      maxWidth: 180,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.black.withAlpha(200),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: SingleChildScrollView(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: _infer.labels.map((l) => Padding(
                          padding: const EdgeInsets.symmetric(vertical: 1),
                          child: Text(
                            '• ${labelZh(l)}  ($l)',
                            style: const TextStyle(
                              color: Colors.white70, fontSize: 10),
                          ),
                        )).toList(),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // FPS / 偵測數 徽章
  Widget _statBadge(IconData icon, String value, String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withAlpha(25),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withAlpha(70), width: 0.8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 4),
          Text(value,
              style: TextStyle(
                  color: color, fontSize: 12, fontWeight: FontWeight.bold)),
          const SizedBox(width: 2),
          Text(label,
              style: TextStyle(color: color.withAlpha(160), fontSize: 10)),
        ],
      ),
    );
  }

  // 效能監控徽章
  Widget _hwChip(IconData icon, String value, String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withAlpha(25),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withAlpha(70), width: 0.8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 11, color: color),
          const SizedBox(width: 3),
          Text(value,
              style: TextStyle(
                  color: color, fontSize: 11, fontWeight: FontWeight.bold)),
          const SizedBox(width: 2),
          Text(label,
              style: TextStyle(color: color.withAlpha(160), fontSize: 10)),
        ],
      ),
    );
  }

  Widget _statusBadge(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withAlpha(200),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(text,
          style: const TextStyle(
              color: Colors.black, fontSize: 11, fontWeight: FontWeight.bold)),
    );
  }

  Color _cpuColor(int pct) {
    if (pct >= 80) return Colors.redAccent;
    if (pct >= 50) return Colors.orangeAccent;
    return Colors.lightBlueAccent;
  }

  Color _tempColor(int deg) {
    if (deg >= 50) return Colors.redAccent;
    if (deg >= 40) return Colors.orangeAccent;
    return Colors.lightGreenAccent;
  }

  Widget _buildErrorScreen(String msg) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.error_outline,
                  color: Colors.redAccent, size: 56),
              const SizedBox(height: 16),
              Text(
                msg,
                style: const TextStyle(color: Colors.white, fontSize: 16),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              ElevatedButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('返回'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ── AR 避障描邊繪製 ──────────────────────────────────────────────────
// 仿避障後端 workflow_blindpath._add_obstacle_visualization (2353~2435)：
//   近距離 rgba(255,0,0,1.0) 粗度 3、遠距離 rgba(255,255,0,0.8) 粗度 2，
//   只描邊不填色（填色是盲道專屬語意，障礙物不該占用）。
// curb（路緣石）單獨粉色：之後會另開用途，先跟一般障礙物區隔。
// 近/遠判斷：Detection.isNear = bottomYRatio > 0.7 或 areaRatio > 0.1。
class _DetectionPainter extends CustomPainter {
  final List<Detection> detections;
  final Size imageSize;  // 來源相機影像（直立座標系）尺寸

  _DetectionPainter({
    required this.detections,
    required this.imageSize,
  });

  // 配色常數（避免每幀重建 Paint 物件）
  static const _nearColor = Color(0xFFFF0000);   // 近紅 rgba(255,0,0,1.0)
  static const _farColor  = Color(0xCCFFFF00);   // 遠黃 rgba(255,255,0,0.8)
  static const _curbColor = Color(0xFFFF69B4);   // curb 粉（hot pink）

  @override
  void paint(Canvas canvas, Size size) {
    if (imageSize.width == 0 || imageSize.height == 0) return;
    // BoxFit.cover 等效縮放：取較大比例填滿
    final scale = (size.width / imageSize.width)
        .compareTo(size.height / imageSize.height) >= 0
        ? size.width / imageSize.width
        : size.height / imageSize.height;
    final dx = (size.width - imageSize.width * scale) / 2;
    final dy = (size.height - imageSize.height * scale) / 2;

    for (final det in detections) {
      final isCurb = det.label.toLowerCase() == 'curb';
      final isNear = det.isNear;
      final Color color;
      final double thickness;
      if (isCurb) {
        color = _curbColor;
        thickness = 2.0;
      } else if (isNear) {
        color = _nearColor;
        thickness = 3.0;
      } else {
        color = _farColor;
        thickness = 2.0;
      }

      final stroke = Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = thickness
        ..strokeJoin = StrokeJoin.round;

      final r = Rect.fromLTWH(
        det.box.left * scale + dx,
        det.box.top * scale + dy,
        det.box.width * scale,
        det.box.height * scale,
      );

      final poly = det.polygon;
      if (poly != null && poly.length >= 3) {
        final path = Path();
        path.moveTo(poly[0].dx * scale + dx, poly[0].dy * scale + dy);
        for (int i = 1; i < poly.length; i++) {
          path.lineTo(poly[i].dx * scale + dx, poly[i].dy * scale + dy);
        }
        path.close();
        canvas.drawPath(path, stroke);
      } else {
        // 沒抽到 contour（mask 太小或被 box 切掉）→ 退回畫框
        canvas.drawRect(r, stroke);
      }

      // Label：原名中文 + 置信度；近距離加「(近)」（仿 _add_obstacle_
      // visualization:2382-2383），curb 不加（跟避障近/遠語意無關）
      final name = labelZh(det.label);
      final String text = (!isCurb && isNear)
          ? '$name(近)  ${(det.confidence * 100).toInt()}%'
          : '$name  ${(det.confidence * 100).toInt()}%';
      _drawLabel(canvas, text, r.topLeft, color);
    }
  }

  void _drawLabel(Canvas canvas, String text, Offset pos, Color color) {
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
          color: color,
          fontSize: 13,
          fontWeight: FontWeight.bold,
          shadows: const [Shadow(color: Colors.black, blurRadius: 4)],
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    final bg = Rect.fromLTWH(pos.dx, pos.dy - 22, tp.width + 10, 22);
    canvas.drawRRect(
      RRect.fromRectAndRadius(bg, const Radius.circular(4)),
      Paint()..color = Colors.black.withAlpha(160),
    );
    tp.paint(canvas, Offset(pos.dx + 5, pos.dy - 20));
  }

  @override
  bool shouldRepaint(covariant _DetectionPainter old) =>
      old.detections != detections || old.imageSize != imageSize;
}
