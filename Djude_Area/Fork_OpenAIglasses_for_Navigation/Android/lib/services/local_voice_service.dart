// lib/services/local_voice_service.dart
// 本地語音服務：從 assets/audio/ 播放預錄 WAV，取代 /stream.wav 傳輸
//
// 使用方式：
//   await LocalVoiceService.instance.init();          // 啟動時呼叫一次
//   int? ms = await LocalVoiceService.instance.speak(text); // 命中回傳時長，未命中回傳 null

import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:audioplayers/audioplayers.dart';

class LocalVoiceService {
  LocalVoiceService._();
  static final instance = LocalVoiceService._();

  // text → {file: "abc123.wav", duration_ms: 1640}
  final Map<String, Map<String, dynamic>> _map = {};
  bool _ready = false;
  bool get ready => _ready;

  // 獨立播放器，與 /stream.wav 播放器互不干擾
  final AudioPlayer _player = AudioPlayer();

  /// 載入 assets/voice_map.json，僅需呼叫一次
  Future<void> init() async {
    try {
      final raw = await rootBundle.loadString('assets/voice_map.json');
      final data = jsonDecode(raw) as Map<String, dynamic>;
      for (final entry in data.entries) {
        _map[entry.key] = Map<String, dynamic>.from(entry.value as Map);
      }
      _ready = true;
      debugPrint('[LocalVoice] 載入 ${_map.length} 筆語音映射');
    } catch (e) {
      debugPrint('[LocalVoice] 初始化失敗: $e');
    }
  }

  /// 播放本地語音，命中回傳 duration_ms，未命中回傳 null
  Future<int?> speak(String text) async {
    if (!_ready) return null;

    final info = _map[text];
    if (info == null) return null;

    final fname = info['file'] as String?;
    if (fname == null) return null;

    try {
      await _player.stop();
      await _player.play(AssetSource('audio/$fname'));
      final ms = (info['duration_ms'] as num?)?.toInt() ?? 2000;
      debugPrint('[LocalVoice] 播放: $text ($ms ms)');
      return ms;
    } catch (e) {
      debugPrint('[LocalVoice] 播放失敗: $text → $e');
      return null;
    }
  }

  void dispose() {
    _player.dispose();
  }
}
