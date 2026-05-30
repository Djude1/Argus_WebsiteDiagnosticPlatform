// lib/services/voice_cache_service.dart
// 預載語音快取：首次啟動時用 flutter_tts 合成固定語句到檔案，
// 之後直接播放音檔（跳過 TTS 引擎延遲，回應更快）。
//
// 設計：
// - 固定語句清單寫在 _phrases 裡，修改後首次啟動會自動重新合成
// - 音檔儲存在 APP 快取目錄，不佔永久空間
// - speak() 命中快取 → AudioPlayer 直接播放
// - speak() 未命中 → 回傳 false，由呼叫端降級到 flutter_tts

import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:audioplayers/audioplayers.dart';
import 'package:path_provider/path_provider.dart';
import 'dart:convert';

class VoiceCacheService {
  VoiceCacheService._();
  static final instance = VoiceCacheService._();

  // ── 需要預載的固定語句 ──────────────────────────────────────────────────
  static const List<String> _phrases = [
    '開始避障導航',
    '開始過馬路模式',
    '開始紅綠燈偵測',
    '已停止所有功能',
    '已停止導航，避障功能繼續運作',
    '已停止避障',
    '請開啟手機定位功能',
    '需要位置權限才能導航',
    '位置權限已被永久拒絕，請至設定中開啟',
    'GPS 啟動失敗，請確認已開啟定位權限',
    '此地點沒有座標，無法啟動導航。請編輯地點填入地址',
    '已記錄為誤判，感謝回饋',
    '已記錄，請注意安全',
    '已取消自動撥打',
  ];

  final AudioPlayer _player = AudioPlayer();
  final Map<String, String> _cache = {}; // text → filePath
  bool _ready = false;
  bool get ready => _ready;

  /// 初始化：在背景合成所有固定語句（不阻塞 UI）
  Future<void> init(FlutterTts tts) async {
    try {
      final dir = await getTemporaryDirectory();
      final cacheDir = Directory('${dir.path}/voice_cache');
      if (!cacheDir.existsSync()) cacheDir.createSync();

      int cached = 0;
      for (final text in _phrases) {
        // 用 text 的 UTF-8 bytes 做簡單 hash，避免檔名含中文
        final hash = utf8.encode(text).fold<int>(0, (h, b) => h * 31 + b).toRadixString(16);
        final path = '${cacheDir.path}/$hash.wav';
        _cache[text] = path;

        // 已存在且大小合理 → 跳過合成
        final file = File(path);
        if (file.existsSync() && file.lengthSync() > 500) {
          cached++;
          continue;
        }

        // 合成到檔案
        try {
          await tts.synthesizeToFile(text, path);
          // synthesizeToFile 是非同步的，等一下讓檔案寫完
          await Future.delayed(const Duration(milliseconds: 300));
          if (File(path).existsSync()) cached++;
        } catch (e) {
          debugPrint('[VoiceCache] 合成失敗: $text → $e');
        }
      }

      _ready = true;
      debugPrint('[VoiceCache] 預載完成：$cached/${_phrases.length} 筆');
    } catch (e) {
      debugPrint('[VoiceCache] 初始化失敗: $e');
    }
  }

  /// 嘗試播放快取語音，命中回傳 true，未命中回傳 false
  Future<bool> speak(String text) async {
    if (!_ready) return false;

    final path = _cache[text];
    if (path == null) return false;

    final file = File(path);
    if (!file.existsSync() || file.lengthSync() < 500) return false;

    try {
      await _player.stop();
      await _player.play(DeviceFileSource(path));
      return true;
    } catch (e) {
      debugPrint('[VoiceCache] 播放失敗: $e');
      return false;
    }
  }

  void dispose() {
    _player.dispose();
  }
}
