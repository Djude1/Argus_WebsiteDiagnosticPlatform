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

  /// chime 播放結束時觸發 — audioplayers 播 chime 時 Android AudioFlinger
  /// 會暫停 voiceRecognition AudioRecord 的 callback，chime 結束不會自動
  /// 恢復。註冊此 callback 以主動 restart mic（由 app_provider 連到
  /// AudioService.restartMicNow）。
  void Function()? onChimeComplete;

  /// 載入 assets/voice_map.json，僅需呼叫一次
  Future<void> init() async {
    try {
      final raw = await rootBundle.loadString('assets/voice_map.json');
      final data = jsonDecode(raw) as Map<String, dynamic>;
      for (final entry in data.entries) {
        _map[entry.key] = Map<String, dynamic>.from(entry.value as Map);
      }
      // ── 關鍵：usage=media（走 STREAM_MUSIC，音量跟導航廣播一致）
      //         + audioFocus=gainTransientMayDuck（短暫 focus + 允許 duck）
      // 預設 audioplayers 用 audioFocus=gain，會通知 Android 系統釋放其他
      // audio session → mic 的 voiceRecognition AudioRecord 被暫停 → chime 播完
      // 不主動 release focus → mic 持續啞掉直到 audio_service watchdog 5 秒
      // 超時強制 restart（實測 WAKE → mic 真正恢復差 7 秒）。
      // gainTransientMayDuck = AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK：
      //   - 申請短暫 focus，不會 pause AudioRecord
      //   - 其他 audio output 被 duck 而非 pause
      //   - chime 結束系統自動 release，mic 立刻恢復
      // contentType/usageType 保持 music/media 以對齊原本 chime 音量（走 STREAM_MUSIC）
      await _player.setAudioContext(
        AudioContext(
          android: AudioContextAndroid(
            isSpeakerphoneOn: false,
            stayAwake: false,
            contentType: AndroidContentType.music,
            usageType: AndroidUsageType.media,
            audioFocus: AndroidAudioFocus.gainTransientMayDuck,
          ),
          iOS: AudioContextIOS(
            category: AVAudioSessionCategory.playAndRecord,
            options: const {AVAudioSessionOptions.mixWithOthers},
          ),
        ),
      );
      // 對齊 audio_service stream player 音量：強制 1.0，避免 chime 比導航廣播小聲
      await _player.setVolume(1.0);
      // 監聽 player state 變化：
      //   1. DEBUG：印 state 時戳
      //   2. completed → 觸發 onChimeComplete，讓 app_provider 主動 restart mic
      //      （audioplayers 播 chime 期間 Android 暫停 AudioRecord，不會自動恢復）
      _player.onPlayerStateChanged.listen((state) {
        debugPrint('[LocalVoice-STATE] $state @ ${DateTime.now().toIso8601String()}');
        if (state == PlayerState.completed) {
          try {
            onChimeComplete?.call();
          } catch (e) {
            debugPrint('[LocalVoice] onChimeComplete error: $e');
          }
        }
      });
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
      final t0 = DateTime.now();
      debugPrint('[LocalVoice-SPEAK] start: "$text" @ ${t0.toIso8601String()}');
      await _player.stop();
      debugPrint('[LocalVoice-SPEAK] after stop(): ${DateTime.now().difference(t0).inMilliseconds}ms');
      await _player.setVolume(1.0);   // defensive：防止某次被改後遺留
      await _player.play(AssetSource('audio/$fname'));
      debugPrint('[LocalVoice-SPEAK] after play(): ${DateTime.now().difference(t0).inMilliseconds}ms');
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
