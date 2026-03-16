// lib/services/audio_service.dart
// 音訊服務：
//   1. 麥克風 PCM16 錄音 → WebSocket 上行
//   2. /stream.wav HTTP 下行播放（TTS）
//   3. 前台服務背景監聽（喚醒詞偵測）

import 'dart:async';
import 'dart:typed_data';
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

  Future<void> playStreamWav(String host, int port) async {
    final url = AppConstants.streamWav(host, port);
    await _player.play(UrlSource(url));
  }

  Future<void> stopPlayback() async {
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
