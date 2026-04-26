// lib/services/yoloe_inference.dart
// 手機端 yoloe-26n-seg ONNX 推論管線（避障專用，仿 obstacle_detector_client.detect）
// 對應計畫：MD/plan_mobile_yolo_deployment.md Phase 3.1
//
// 定位：只做「避開障礙」— 偵測白名單類別 → 回傳 box + polygon +
//       area_ratio + bottom_y_ratio，交給 painter 依「近紅遠黃、只描邊」畫。
//       不做室內/室外區分（以後若要再加，另開切換）。
//
// 流程：CameraImage(YUV420) → 主 isolate copy plane bytes
//      → compute(_preprocessIsolate) → background isolate 跑 YUV→RGB→letterbox→CHW
//      → 主 isolate 拿 Float32List → OrtSession.runAsync (native worker thread)
//      → 主 isolate 把 outputs[0]、outputs[1] 攤平成 Float32List（OrtEnv 是 FFI
//        singleton 不能跨 isolate；onnxruntime 套件 value getter 沒 zero-copy，
//        ~150-200ms 卡 UI 是已知代價）
//      → compute(_decodeIsolate) → background isolate 跑 NMS + mask sigmoid +
//        Moore neighbor tracing 抽外輪廓 → 旋轉 90° CW → polygon points，
//        並計算 area_ratio / bottom_y_ratio（規則同 obstacle_detector_client）
//      → 主 isolate 拿 List<Detection>，CustomPainter 依近/遠上色描邊
//
// 仿避障後端 obstacle_detector_client.detect 與 workflow_blindpath.
// _add_obstacle_visualization：area_ratio > 0.7 視為誤判（整片地面）過濾掉，
// bottom_y_ratio > 0.7 或 area_ratio > 0.1 視為近距離。

import 'dart:async';
import 'dart:convert';
import 'dart:ui' show Offset, Rect;

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:image/image.dart' as img;
import 'package:onnxruntime/onnxruntime.dart';

import '../screens/yoloe_ar_test_screen.dart' show Detection, InferResult;

// 與伺服器 obstacle_detector_client.WHITELIST_CLASSES 保持同步
// 保留原始標籤名，不改叫大/中/小障礙物
const Set<String> _kObstacleWhitelist = {
  'person', 'bicycle', 'car', 'motorcycle', 'bus', 'truck',
  'animal', 'scooter', 'stroller', 'dog',
  'pole', 'post', 'bollard', 'utility pole', 'light pole', 'signpost',
  'bench', 'chair', 'potted plant', 'hydrant', 'cone', 'stone', 'box',
  'trash can', 'barrel', 'cart',
  'fence', 'barrier', 'wall', 'gate', 'door',
  'rock', 'tree', 'branch', 'curb',
  'stairs', 'step', 'ramp', 'hole',
  'bag', 'suitcase', 'backpack',
  'table', 'ladder',
  'object', 'obstacle',
};

class YoloeInference {
  static const int imgsz = 640;
  static const double _defaultConfTh = 0.25;
  static const double _iouTh = 0.50;

  // mask proto 解析度（YOLOE-seg 預設 160×160）
  static const int _maskHW = 160;
  // mask 160 對應 letterbox 640，比例 = 640/160 = 4
  static const int _maskScale = 4;
  // contour 抽樣率：每 N 點取 1 點，跟避障 contour[::5] 同概念
  static const int _polyStride = 3;

  OrtSession? _session;
  List<String> _labels = const [];
  String _inputName = 'images';    // 動態讀自模型 metadata，避免匯出名稱差異
  bool _busy = false;             // 上一幀尚未推完 → 本幀 skip
  bool _disposed = false;          // 防止 release 後仍被呼叫 infer
  int _debugCnt = 0;               // throttle debug log
  double confTh = _defaultConfTh;

  bool get isReady => _session != null && !_disposed;
  List<String> get labels => _labels;
  bool get isBusy => _busy;

  /// 固定載入 outdoor 避障模型。室內/室外切換現已移除（只做避障，不分場景）。
  /// 若未來要恢復切換，再獨立開 API，不要回到 enum Scene 的架構。
  Future<void> init() async {
    OrtEnv.instance.init();
    const modelAsset = 'assets/models/yoloe_26n_seg_outdoor.onnx';
    const labelAsset = 'assets/models/outdoor_labels.json';

    final modelBytes =
        (await rootBundle.load(modelAsset)).buffer.asUint8List();
    _session?.release();
    final opts = OrtSessionOptions();
    _session = OrtSession.fromBuffer(modelBytes, opts);
    opts.release();
    // 動態取得 ONNX 輸入節點名稱，避免匯出時名稱不是 'images'
    final names = _session!.inputNames;
    _inputName = names.isNotEmpty ? names.first : 'images';

    final labelStr = await rootBundle.loadString(labelAsset);
    _labels = (jsonDecode(labelStr) as List).cast<String>();
    debugPrint('[YoloeInference] 模型輸入名稱: $_inputName, 標籤數: ${_labels.length}');
  }

  /// 安全釋放：先擋掉新的 infer，再等正在跑的 native runAsync 結束，最後才 release。
  /// 不這樣做會 SIGSEGV — Activity dispose 時 native worker 還握著舊 session。
  Future<void> dispose() async {
    _disposed = true;
    for (int i = 0; i < 200; i++) {
      if (!_busy) break;
      await Future.delayed(const Duration(milliseconds: 10));
    }
    try {
      _session?.release();
      _session = null;
      OrtEnv.instance.release();
    } catch (e) {
      debugPrint('[YoloeInference] dispose release error: $e');
    }
  }

  /// 對單幀做推論。未 ready / 已 dispose / 前一幀未完成 → 回 null（呼叫端應 skip）。
  Future<InferResult?> infer(CameraImage frame) async {
    if (_disposed || _session == null || _busy) return null;
    // 在 try 外先取得尺寸，讓 catch 也能用正確的 srcW/srcH
    final srcW = frame.width;
    final srcH = frame.height;
    _busy = true;
    try {
      // (1) 主 isolate：copy plane bytes（跨 isolate 傳遞需可序列化）
      final req = _PreReq(
        y: Uint8List.fromList(frame.planes[0].bytes),
        u: Uint8List.fromList(frame.planes[1].bytes),
        v: Uint8List.fromList(frame.planes[2].bytes),
        yStride: frame.planes[0].bytesPerRow,
        uvStride: frame.planes[1].bytesPerRow,
        uvPixelStride: frame.planes[1].bytesPerPixel ?? 1,
        width: frame.width,
        height: frame.height,
      );

      // (2) background isolate：YUV→RGB → letterbox 640 → CHW Float32 0-1
      final pre = await compute(_preprocessIsolate, req);

      // (3) 主 isolate：runAsync 將推論丟進 native worker thread，主執行緒只是 await，
      //   不阻塞 Flutter 渲染管線。例外由外層 try-catch 捕捉，_busy 由 finally 釋放。
      //   （舊版改用同步 run() 是誤解：run() 把整個 CPU 推論時間 ~2-3s 完整卡在主執行緒，
      //     是 Davey 3-4 秒的直接原因）
      final input = OrtValueTensor.createTensorWithDataList(
        pre.data,
        [1, 3, imgsz, imgsz],
      );
      final runOpts = OrtRunOptions();
      final List<OrtValue?>? rawOutputs =
          await _session!.runAsync(runOpts, {_inputName: input});
      input.release();
      runOpts.release();

      if (rawOutputs == null || rawOutputs.isEmpty) {
        debugPrint('[YoloeInference] runAsync() 回傳空 outputs');
        return InferResult(detections: const [], srcW: srcW, srcH: srcH);
      }
      final outputs = rawOutputs;

      // 主 isolate 攤平兩個輸出 — OrtValue.value 是 dynamic List，
      // 跨 isolate 無法傳遞且 reshape 內部 num.toDouble()（這就是 ~150ms 的瓶頸）。
      final raw0 = outputs[0]?.value;
      final raw1 = outputs.length > 1 ? outputs[1]?.value : null;
      for (final o in outputs) {
        o?.release();
      }
      if (raw0 is! List) {
        debugPrint('[YoloeInference] output0.value 非 List，實際型別=${raw0.runtimeType}');
        return InferResult(detections: const [], srcW: srcW, srcH: srcH);
      }

      final flat0 = _flatten3D(raw0);
      Float32List? flat1;
      int proto1C = 0, proto1H = 0, proto1W = 0;
      if (raw1 is List) {
        final shape = _shape4D(raw1);
        proto1C = shape[1];
        proto1H = shape[2];
        proto1W = shape[3];
        flat1 = _flatten4D(raw1);
      }

      final nc = _labels.length;
      final numAnchors = flat0.length ~/ (4 + nc + 32);

      // (4) background isolate：NMS + mask 解碼 + Moore tracing → polygon
      final decoded = await compute(_decodeIsolate, _DecodeReq(
        output0: flat0,
        output1: flat1 ?? Float32List(0),
        proto1HasData: flat1 != null,
        proto1C: proto1C,
        proto1H: proto1H,
        proto1W: proto1W,
        nc: nc,
        numAnchors: numAnchors,
        scale: pre.scale,
        padX: pre.padX,
        padY: pre.padY,
        effW: pre.effW,
        effH: pre.effH,
        confTh: confTh,
        iouTh: _iouTh,
        labels: _labels,
        imgsz: imgsz,
        maskHW: _maskHW,
        maskScale: _maskScale,
        polyStride: _polyStride,
      ));

      _debugCnt++;
      if (_debugCnt % 10 == 0) {
        final first = decoded.detections.isNotEmpty ? decoded.detections.first : null;
        debugPrint(
          '[YoloeInference] frame=${srcW}x$srcH '
          'scale=${pre.scale.toStringAsFixed(3)} '
          'pad=(${pre.padX},${pre.padY}) '
          'globalMax=${decoded.globalMaxConf.toStringAsFixed(3)} '
          'confPass=${decoded.dbgConfPass} nmsKeep=${decoded.dbgNmsKeep} '
          'box=${decoded.dbgBox} area=${decoded.dbgArea} wl=${decoded.dbgWl} '
          'dets=${decoded.detections.length} '
          'first=${first == null ? "none" : "${first.label} ${(first.confidence * 100).toInt()}% poly=${first.polygon?.length ?? 0}pt"}',
        );
      }

      return InferResult(
        detections: decoded.detections,
        srcW: srcW,
        srcH: srcH,
        globalMaxConf: decoded.globalMaxConf,
      );
    } catch (e, st) {
      debugPrint('[YoloeInference] infer error: $e\n$st');
      return InferResult(detections: const [], srcW: srcW, srcH: srcH);
    } finally {
      _busy = false;
    }
  }

  // 攤平 (1, A, B) → Float32List length A*B（row-major）
  static Float32List _flatten3D(List raw) {
    final outer = raw[0] as List;
    final a = outer.length;
    final b = (outer[0] as List).length;
    final out = Float32List(a * b);
    for (int i = 0; i < a; i++) {
      final row = (outer[i] as List).cast<num>();
      final base = i * b;
      for (int j = 0; j < b; j++) {
        out[base + j] = row[j].toDouble();
      }
    }
    return out;
  }

  // 攤平 (1, C, H, W) → Float32List length C*H*W（row-major）
  static Float32List _flatten4D(List raw) {
    final c0 = raw[0] as List;
    final c = c0.length;
    final h = (c0[0] as List).length;
    final w = ((c0[0] as List)[0] as List).length;
    final out = Float32List(c * h * w);
    int idx = 0;
    for (int ci = 0; ci < c; ci++) {
      final hRows = c0[ci] as List;
      for (int hi = 0; hi < h; hi++) {
        final wRow = (hRows[hi] as List).cast<num>();
        for (int wi = 0; wi < w; wi++) {
          out[idx++] = wRow[wi].toDouble();
        }
      }
    }
    return out;
  }

  static List<int> _shape4D(List raw) {
    final c0 = raw[0] as List;
    final c = c0.length;
    final h = (c0[0] as List).length;
    final w = ((c0[0] as List)[0] as List).length;
    return [1, c, h, w];
  }
}

// ────────────────────────────────────────────────────────────────────
// 跨 isolate 跑的前處理（top-level，compute() 限制必須是 top-level/static）
// ────────────────────────────────────────────────────────────────────

class _PreReq {
  final Uint8List y, u, v;
  final int yStride, uvStride, uvPixelStride;
  final int width, height;
  const _PreReq({
    required this.y,
    required this.u,
    required this.v,
    required this.yStride,
    required this.uvStride,
    required this.uvPixelStride,
    required this.width,
    required this.height,
  });
}

class _PreRes {
  final Float32List data;
  final double scale;
  final int padX, padY;
  final int effW, effH;  // 旋轉後送入模型的有效尺寸（effW=原srcH, effH=原srcW）
  const _PreRes({
    required this.data,
    required this.scale,
    required this.padX,
    required this.padY,
    required this.effW,
    required this.effH,
  });
}

const int _kImgsz = 640;

/// background isolate：YUV420 → RGB → letterbox 640×640 → CHW Float32 0-1
_PreRes _preprocessIsolate(_PreReq req) {
  final w = req.width, h = req.height;

  // 1. YUV→RGB（BT.601 limited，純整數運算）
  final rgb = Uint8List(w * h * 3);
  int idx = 0;
  for (int y = 0; y < h; y++) {
    final yRow = y * req.yStride;
    final uvRow = (y >> 1) * req.uvStride;
    for (int x = 0; x < w; x++) {
      final yp = req.y[yRow + x];
      final uvCol = (x >> 1) * req.uvPixelStride;
      final up = req.u[uvRow + uvCol];
      final vp = req.v[uvRow + uvCol];
      final u = up - 128;
      final v = vp - 128;
      int r = yp + ((1436 * v) >> 10);
      int g = yp - ((352 * u + 731 * v) >> 10);
      int b = yp + ((1814 * u) >> 10);
      if (r < 0) {
        r = 0;
      } else if (r > 255) {
        r = 255;
      }
      if (g < 0) {
        g = 0;
      } else if (g > 255) {
        g = 255;
      }
      if (b < 0) {
        b = 0;
      } else if (b > 255) {
        b = 255;
      }
      rgb[idx++] = r;
      rgb[idx++] = g;
      rgb[idx++] = b;
    }
  }

  // 2. 旋轉 90° CW：Android 後鏡頭 sensor 橫向傳送，直立持機時 YOLO 收到側倒影像
  //    (max conf≈0.06)；旋轉後人物直立，conf 可回到正常水準（0.5+）。
  //    img.copyRotate 正角度=CCW，angle:-90 = 90° CW；大多數 Android 後鏡頭適用。
  //    若旋轉後仍無偵測，嘗試 angle:90（少數裝置 sensor 方向相反）。
  final src = img.Image.fromBytes(
    width: w,
    height: h,
    bytes: rgb.buffer,
    order: img.ChannelOrder.rgb,
  );
  final rotated = img.copyRotate(src, angle: -90);
  final rW = rotated.width;   // = h（原 landscape H → portrait W，e.g. 720）
  final rH = rotated.height;  // = w（原 landscape W → portrait H，e.g. 1280）

  // 3. Letterbox：等比 resize 貼到 114 背景
  final r = (_kImgsz / rW) < (_kImgsz / rH) ? _kImgsz / rW : _kImgsz / rH;
  final newW = (rW * r).round();
  final newH = (rH * r).round();
  final padX = (_kImgsz - newW) ~/ 2;
  final padY = (_kImgsz - newH) ~/ 2;

  final resized = img.copyResize(rotated,
      width: newW, height: newH, interpolation: img.Interpolation.linear);
  final canvas = img.Image(width: _kImgsz, height: _kImgsz);
  img.fill(canvas, color: img.ColorRgb8(114, 114, 114));
  img.compositeImage(canvas, resized, dstX: padX, dstY: padY);

  // 3. HWC u8 → CHW f32 0-1
  final bytes = canvas.getBytes(order: img.ChannelOrder.rgb);
  final n = _kImgsz * _kImgsz;
  final out = Float32List(3 * n);
  for (int i = 0; i < n; i++) {
    out[i] = bytes[i * 3] / 255.0;             // R
    out[n + i] = bytes[i * 3 + 1] / 255.0;     // G
    out[2 * n + i] = bytes[i * 3 + 2] / 255.0; // B
  }
  return _PreRes(data: out, scale: r, padX: padX, padY: padY, effW: rW, effH: rH);
}

// ────────────────────────────────────────────────────────────────────
// 跨 isolate 跑的後處理：NMS + mask 解碼 + Moore tracing → polygon
// ────────────────────────────────────────────────────────────────────

class _DecodeReq {
  final Float32List output0;     // (4+nc+32) × numAnchors，row-major
  final Float32List output1;     // 32 × maskHW × maskHW，row-major
  final bool proto1HasData;
  final int proto1C, proto1H, proto1W;
  final int nc;
  final int numAnchors;          // 通常 8400
  final double scale;
  final int padX, padY;
  final int effW, effH;  // 旋轉後有效尺寸（portrait：effW=原srcH, effH=原srcW）
  final double confTh, iouTh;
  final List<String> labels;
  final int imgsz;
  final int maskHW;              // 160
  final int maskScale;           // 4：letterbox 640 → mask 160
  final int polyStride;          // 抽樣 contour，每 N 點取 1 點
  const _DecodeReq({
    required this.output0,
    required this.output1,
    required this.proto1HasData,
    required this.proto1C,
    required this.proto1H,
    required this.proto1W,
    required this.nc,
    required this.numAnchors,
    required this.scale,
    required this.padX,
    required this.padY,
    required this.effW,
    required this.effH,
    required this.confTh,
    required this.iouTh,
    required this.labels,
    required this.imgsz,
    required this.maskHW,
    required this.maskScale,
    required this.polyStride,
  });
}

// _decodeIsolate 回傳結構：偵測結果 + 全域最高分 + 各過濾器計數（診斷用）
class _DecodeResult {
  final List<Detection> detections;
  final double globalMaxConf;
  final int dbgConfPass;  // 通過 confTh 的候選數
  final int dbgNmsKeep;   // NMS 後保留數
  final int dbgBox;       // box 無效被丟棄數
  final int dbgArea;      // areaRatio 超標被丟棄數
  final int dbgWl;        // whitelist 不符被丟棄數
  const _DecodeResult(this.detections, this.globalMaxConf,
      {this.dbgConfPass = 0, this.dbgNmsKeep = 0,
       this.dbgBox = 0, this.dbgArea = 0, this.dbgWl = 0});
}

_DecodeResult _decodeIsolate(_DecodeReq req) {
  final na = req.numAnchors;
  final nc = req.nc;
  if (na <= 0 || nc <= 0 || req.output0.length < (4 + nc) * na) {
    return _DecodeResult(const [], 0.0);
  }

  // ── 1. 候選收集（letterbox 座標） ──
  final boxes = <List<double>>[];
  final scores = <double>[];
  final ids = <int>[];
  final anchors = <int>[];

  // 掃描全域最高信心分數（回傳給主執行緒顯示，方便診斷）
  double globalMax = 0.0;
  for (int a = 0; a < na; a++) {
    for (int c = 0; c < nc; c++) {
      final s = req.output0[(4 + c) * na + a];
      if (s > globalMax) globalMax = s;
    }
  }

  for (int a = 0; a < na; a++) {
    double maxConf = 0.0;
    int maxId = -1;
    for (int c = 0; c < nc; c++) {
      final s = req.output0[(4 + c) * na + a];
      if (s > maxConf) {
        maxConf = s;
        maxId = c;
      }
    }
    if (maxConf < req.confTh || maxId < 0) continue;
    final cx = req.output0[a];
    final cy = req.output0[na + a];
    final bw = req.output0[2 * na + a];
    final bh = req.output0[3 * na + a];
    boxes.add([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2]);
    scores.add(maxConf);
    ids.add(maxId);
    anchors.add(a);
  }

  if (boxes.isEmpty) return _DecodeResult(const [], globalMax);

  final keep = _isoNms(boxes, scores, req.iouTh);

  final hasProto = req.proto1HasData &&
      req.proto1C == 32 &&
      req.proto1H == req.maskHW &&
      req.proto1W == req.maskHW &&
      req.output1.length == 32 * req.maskHW * req.maskHW;

  // ── 2. 對每個 keep 解 mask binary（在 mask 160 box 範圍內），抽 contour，
  //      座標反推 → portrait polygon ──
  final dets = <Detection>[];
  final coef = Float32List(32);
  final mhw = req.maskHW * req.maskHW;
  final ms = req.maskScale.toDouble();
  final maxLI = (req.imgsz - 1).toDouble();
  final srcWf = req.effW.toDouble();  // portrait 寬（旋轉後 effW = 原 srcH）
  final srcHf = req.effH.toDouble();  // portrait 高（旋轉後 effH = 原 srcW）

  // 診斷計數器（每幀都印，方便即時定位過濾瓶頸）
  int dbgBox = 0, dbgArea = 0, dbgWl = 0;

  for (final i in keep) {
    final a = anchors[i];

    // 還原 box 至 portrait（letterbox 反轉；preprocess 已旋轉，不需再旋轉）
    double bx1 = (boxes[i][0] - req.padX) / req.scale;
    double by1 = (boxes[i][1] - req.padY) / req.scale;
    double bx2 = (boxes[i][2] - req.padX) / req.scale;
    double by2 = (boxes[i][3] - req.padY) / req.scale;
    if (bx1 < 0) bx1 = 0;
    if (by1 < 0) by1 = 0;
    if (bx2 > srcWf) bx2 = srcWf;  // clamp to portrait W
    if (by2 > srcHf) by2 = srcHf;  // clamp to portrait H
    if (bx2 <= bx1 || by2 <= by1) { dbgBox++; continue; }
    final boxPort = Rect.fromLTWH(bx1, by1, bx2 - bx1, by2 - by1);

    List<Offset>? polygon;
    int maskFgCount = 0;   // 前景像素數：算 area_ratio 用；無 mask 時退回 box 面積
    if (hasProto) {
      // 取 32 個 mask coef
      for (int c = 0; c < 32; c++) {
        coef[c] = req.output0[(4 + nc + c) * na + a];
      }

      // box 在 mask 160 中的範圍（夾邊）
      double lx1 = boxes[i][0];
      double ly1 = boxes[i][1];
      double lx2 = boxes[i][2];
      double ly2 = boxes[i][3];
      if (lx1 < 0) lx1 = 0;
      if (ly1 < 0) ly1 = 0;
      if (lx2 > maxLI) lx2 = maxLI;
      if (ly2 > maxLI) ly2 = maxLI;
      int mxs = (lx1 / ms).floor();
      int mys = (ly1 / ms).floor();
      int mxe = (lx2 / ms).ceil();
      int mye = (ly2 / ms).ceil();
      if (mxs < 0) mxs = 0;
      if (mys < 0) mys = 0;
      if (mxe > req.maskHW - 1) mxe = req.maskHW - 1;
      if (mye > req.maskHW - 1) mye = req.maskHW - 1;

      // 解 box 範圍內 mask binary（sigmoid(v) > 0.5 ⇔ v > 0）
      final bin = Uint8List(mhw);
      int sx0 = -1, sy0 = -1;   // 起始點：左上掃第一個前景
      for (int my = mys; my <= mye; my++) {
        final rowBase = my * req.maskHW;
        for (int mx = mxs; mx <= mxe; mx++) {
          double v = 0.0;
          final pBase = rowBase + mx;
          for (int c = 0; c < 32; c++) {
            v += coef[c] * req.output1[c * mhw + pBase];
          }
          if (v > 0.0) {
            bin[pBase] = 1;
            maskFgCount++;
            if (sx0 < 0) {
              sx0 = mx;
              sy0 = my;
            }
          }
        }
      }

      if (sx0 >= 0) {
        final raw = _mooreTrace(bin, req.maskHW, req.maskHW, sx0, sy0);
        if (raw.length >= 6) {
          // 抽樣 + 從 mask160 → letterbox → src → portrait
          final pts = <Offset>[];
          for (int k = 0; k < raw.length; k += req.polyStride) {
            final mx = raw[k * 2];
            final my = raw[k * 2 + 1];
            // mask 中心對應 letterbox 中心
            final lx = (mx + 0.5) * ms;
            final ly = (my + 0.5) * ms;
            final px = (lx - req.padX) / req.scale;
            final py = (ly - req.padY) / req.scale;
            pts.add(Offset(px, py));
          }
          if (pts.length >= 3) polygon = pts;
        }
      }
    }

    // area_ratio：仿 obstacle_detector_client.detect。
    // mask 1 px = (maskScale / scale)² src 像素；無 mask 時退回 box 面積。
    // area_ratio > 0.7 視為整片誤判（如整片地面），直接 skip（跟後端一致）。
    final double areaRatio;
    if (maskFgCount > 0) {
      final sf = ms / req.scale;
      areaRatio = maskFgCount * sf * sf / (srcWf * srcHf);
    } else {
      areaRatio = (bx2 - bx1) * (by2 - by1) / (srcWf * srcHf);
    }
    if (areaRatio > 0.9) { dbgArea++; continue; }

    // bottom_y_ratio：portrait 底邊 y（by2）/ portrait 高（effH）
    final bottomYRatio = by2 / srcHf;

    final label = req.labels[ids[i]];
    if (!_kObstacleWhitelist.contains(label)) { dbgWl++; continue; }

    dets.add(Detection(
      label: label,
      confidence: scores[i],
      box: boxPort,
      polygon: polygon,
      areaRatio: areaRatio,
      bottomYRatio: bottomYRatio,
    ));
  }

  return _DecodeResult(dets, globalMax,
      dbgConfPass: boxes.length, dbgNmsKeep: keep.length,
      dbgBox: dbgBox, dbgArea: dbgArea, dbgWl: dbgWl);
}

// ── Moore neighbor tracing：8-connectivity 外輪廓 ─────────────────────
// 回傳 [x0, y0, x1, y1, ...] flat，呼叫端用 raw[k*2], raw[k*2+1] 抽樣。
// 用 flat 而非 List<Offset> 是為了減少 isolate 內 GC pressure。
const List<int> _kNbDx = [0, 1, 1, 1, 0, -1, -1, -1];   // N, NE, E, SE, S, SW, W, NW
const List<int> _kNbDy = [-1, -1, 0, 1, 1, 1, 0, -1];

List<int> _mooreTrace(Uint8List mask, int w, int h, int sx, int sy) {
  final pts = <int>[];
  int x = sx, y = sy;
  // backtrack 方向：起始點是「掃描第一個前景」，左上邊界一定是空的，
  // 預設 backtrack=西(6)，從 west+1=NW(7) 順時針掃下一個鄰居。
  int back = 6;
  pts.add(x);
  pts.add(y);

  // 上限：避免 mask 有破洞時無窮迴圈（最壞情況 4*(w+h)）
  final maxStep = 4 * (w + h);
  for (int step = 0; step < maxStep; step++) {
    int found = -1;
    for (int t = 1; t <= 8; t++) {
      final d = (back + t) & 7;
      final nx = x + _kNbDx[d];
      final ny = y + _kNbDy[d];
      if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
      if (mask[ny * w + nx] == 1) {
        x = nx;
        y = ny;
        // 反方向 = (d + 4) & 7
        back = (d + 4) & 7;
        found = d;
        break;
      }
    }
    if (found < 0) break;     // 孤立點
    if (x == sx && y == sy) break;   // 回到起點
    pts.add(x);
    pts.add(y);
  }
  return pts;
}

List<int> _isoNms(
    List<List<double>> boxes, List<double> scores, double iouTh) {
  final n = boxes.length;
  if (n == 0) return const [];
  final order = List<int>.generate(n, (i) => i)
    ..sort((a, b) => scores[b].compareTo(scores[a]));
  final keep = <int>[];
  final sup = List<bool>.filled(n, false);
  for (int oi = 0; oi < n; oi++) {
    final i = order[oi];
    if (sup[i]) continue;
    keep.add(i);
    for (int oj = oi + 1; oj < n; oj++) {
      final j = order[oj];
      if (sup[j]) continue;
      if (_isoIou(boxes[i], boxes[j]) > iouTh) {
        sup[j] = true;
      }
    }
  }
  return keep;
}

double _isoIou(List<double> a, List<double> b) {
  final x1 = a[0] > b[0] ? a[0] : b[0];
  final y1 = a[1] > b[1] ? a[1] : b[1];
  final x2 = a[2] < b[2] ? a[2] : b[2];
  final y2 = a[3] < b[3] ? a[3] : b[3];
  final w = x2 - x1, h = y2 - y1;
  if (w <= 0 || h <= 0) return 0.0;
  final inter = w * h;
  final areaA = (a[2] - a[0]) * (a[3] - a[1]);
  final areaB = (b[2] - b[0]) * (b[3] - b[1]);
  return inter / (areaA + areaB - inter + 1e-9);
}
