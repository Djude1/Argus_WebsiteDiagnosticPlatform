// lib/services/audio_service.dart
// 音訊服務：
//   1. 麥克風 PCM16 錄音 → WebSocket 上行
//   2. /stream.wav HTTP 下行播放（TTS）
//   3. 前台服務背景監聽（喚醒詞偵測）

import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:record/record.dart';
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import '../core/constants.dart';

typedef PcmChunkCallback = void Function(Uint8List pcm16);
typedef WakeWordCallback  = void Function();

class AudioService {
  // ── 麥克風錄音 ──────────────────────────────────────────────────────────
  final AudioRecorder _recorder = AudioRecorder();
  StreamSubscription? _recordSub;
  bool _recording = false;

  // ── TTS 串流重連狀態 ─────────────────────────────────────────────────────
  bool _shouldPlayStream = false;   // 是否應維持串流播放
  String? _streamUrl;               // 串流 URL（用於重連）
  StreamSubscription<PlayerState>? _playerStateSub; // 播放狀態監聽

  /// 開始錄音並以 PCM16 Chunk 回呼
  Future<void> startMicrophone({required PcmChunkCallback onChunk}) async {
    if (_recording) return;
    _recording = true;

    final stream = await _recorder.startStream(const RecordConfig(
      encoder:    AudioEncoder.pcm16bits,
      sampleRate: 16000,
      numChannels: 1,
    ));

    _recordSub = stream.listen((data) {
      onChunk(Uint8List.fromList(data));
    });
  }

  Future<void> stopMicrophone() async {
    _recording = false;
    await _recordSub?.cancel();
    _recordSub = null;
    await _recorder.stop();
  }

  bool get isRecording => _recording;

  // ── TTS 下行播放 ─────────────────────────────────────────────────────────
  final AudioPlayer _player = AudioPlayer();

  Future<void> playStreamWav(String host, int port,
      {bool secure = false, String? baseUrl}) async {
    final url = AppConstants.streamWav(host, port,
        secure: secure, baseUrl: baseUrl);
    _streamUrl = url;
    _shouldPlayStream = true;

    // 設定音量為最大
    await _player.setVolume(1.0);

    // 取消舊的狀態監聽，重新設置
    await _playerStateSub?.cancel();
    _playerStateSub = _player.onPlayerStateChanged.listen((state) {
      debugPrint('[AudioService] 播放狀態變更: $state');
      // 播放完成或非預期停止時，自動重連伺服器串流
      if (_shouldPlayStream &&
          (state == PlayerState.completed || state == PlayerState.stopped)) {
        debugPrint('[AudioService] 串流中斷，準備重連...');
        _scheduleReconnect();
      }
    });

    // 監聽播放器錯誤
    _player.onLog.listen((msg) {
      debugPrint('[AudioService] 播放器日誌: $msg');
    });

    debugPrint('[AudioService] 連線 /stream.wav: $url');
    try {
      await _player.play(UrlSource(url));
      debugPrint('[AudioService] 播放已啟動');
    } catch (e) {
      debugPrint('[AudioService] 播放失敗: $e');
      _scheduleReconnect();
    }
  }

  /// 延遲後重新連線 /stream.wav（伺服器可能因重置而切斷連線）
  void _scheduleReconnect() {
    if (!_shouldPlayStream || _streamUrl == null) return;
    Future.delayed(const Duration(milliseconds: 800), () async {
      if (!_shouldPlayStream || _streamUrl == null) return;
      debugPrint('[AudioService] 重連 /stream.wav...');
      try {
        await _player.play(UrlSource(_streamUrl!));
        debugPrint('[AudioService] 重連成功');
      } catch (e) {
        debugPrint('[AudioService] 重連失敗: $e');
        // 連線失敗，1 秒後再試
        Future.delayed(const Duration(seconds: 1), _scheduleReconnect);
      }
    });
  }

  Future<void> stopPlayback() async {
    _shouldPlayStream = false;
    _streamUrl = null;
    await _playerStateSub?.cancel();
    _playerStateSub = null;
    await _player.stop();
  }

  // ── 前台服務（背景監聽）─────────────────────────────────────────────────
  bool _foregroundRunning = false;

  Future<void> startForegroundService() async {
    if (_foregroundRunning) return;
    _foregroundRunning = true;

    await FlutterForegroundTask.startService(
      notificationTitle: 'AI智慧眼鏡',
      notificationText:  '背景監聽中，隨時可呼叫語音指令',
      callback: _foregroundTaskCallback,
    );
  }

  Future<void> stopForegroundService() async {
    _foregroundRunning = false;
    await FlutterForegroundTask.stopService();
  }

  bool get isForegroundRunning => _foregroundRunning;

  Future<void> dispose() async {
    _shouldPlayStream = false;
    _streamUrl = null;
    await _playerStateSub?.cancel();
    _playerStateSub = null;
    await stopMicrophone();
    await _player.dispose();
  }
}

/// 前台服務回呼函式（必須是頂層函式）
@pragma('vm:entry-point')
void _foregroundTaskCallback() {
  FlutterForegroundTask.setTaskHandler(_AudioTaskHandler());
}

class _AudioTaskHandler extends TaskHandler {
  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {
    // 前台服務啟動，可在此初始化背景錄音邏輯
  }

  @override
  void onRepeatEvent(DateTime timestamp) {
    // 每 5 秒觸發一次，可用於保活心跳
    FlutterForegroundTask.updateService(
      notificationTitle: 'AI智慧眼鏡',
      notificationText:  '背景監聽中 ${_timeStr(timestamp)}',
    );
  }

  @override
  Future<void> onDestroy(DateTime timestamp) async {}

  String _timeStr(DateTime t) =>
      '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
}
