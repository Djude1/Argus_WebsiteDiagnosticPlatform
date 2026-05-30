// lib/services/audio_service.dart
// 音訊服務：
//   1. 麥克風 PCM16 錄音 → WebSocket 上行
//   2. /stream.wav HTTP 下行播放（TTS）
//   3. 前台服務背景監聽（喚醒詞偵測）

import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:record/record.dart';
import 'package:just_audio/just_audio.dart' as ja;
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import '../core/constants.dart';

typedef PcmChunkCallback = void Function(Uint8List pcm16);
typedef WakeWordCallback  = void Function();

class AudioService {
  // ── 麥克風錄音 ──────────────────────────────────────────────────────────
  final AudioRecorder _recorder = AudioRecorder();
  StreamSubscription? _recordSub;
  bool _recording = false;
  PcmChunkCallback? _onChunkCb;        // 保存 callback 供自動重啟使用
  DateTime _lastChunkAt = DateTime.now();
  Timer? _micWatchdog;
  bool _restarting = false;            // 防止 onError + watchdog 同時重啟

  // DEBUG：mic 幀率追蹤（每秒印一次）— 診斷「WAKE 後 mic 不送幀」
  int _micChunkCountWindow = 0;
  int _micBytesWindow = 0;
  DateTime _micRateWindowStart = DateTime.now();

  // DEBUG：mic 全域累計（給 app_provider 在 cycle 結束時印 summary）
  int _micTotalChunks = 0;
  int _micTotalSamples = 0;
  int get micTotalChunks => _micTotalChunks;
  int get micTotalSamples => _micTotalSamples;
  void resetMicCounter() {
    _micTotalChunks = 0;
    _micTotalSamples = 0;
  }

  // ── TTS 串流重連狀態 ─────────────────────────────────────────────────────
  bool _shouldPlayStream = false;   // 是否應維持串流播放
  bool _isReconnecting   = false;   // 防止多個重連同時觸發
  String? _streamUrl;               // 串流 URL（用於重連）
  StreamSubscription<ja.PlayerState>? _playerStateSub; // 播放狀態監聽（just_audio）

  /// 開始錄音並以 PCM16 Chunk 回呼
  Future<void> startMicrophone({required PcmChunkCallback onChunk}) async {
    if (_recording) return;
    _recording = true;
    _onChunkCb = onChunk;

    await _startInternal();
    _startMicWatchdog();
  }

  /// 內部啟動 stream（首次啟動 + 自動重啟共用）
  Future<void> _startInternal() async {
    // 音源用 voiceRecognition：Android 專為 ASR 設計的音源，內建合理的
    // noise suppression，但不會像 voiceCommunication 過度抑制把人聲也消掉
    // （voiceCommunication 是「雙工通話」音源，AEC 過強會讓 RMS 降到 0~2，
    //   實測在 server 端整段對話完全收不到人聲）。
    // 不設 audioManagerMode：避免改變系統音訊路由造成裝置間行為差異。
    final stream = await _recorder.startStream(const RecordConfig(
      encoder:    AudioEncoder.pcm16bits,
      sampleRate: 16000,
      numChannels: 1,
      androidConfig: AndroidRecordConfig(
        audioSource: AndroidAudioSource.voiceRecognition,
      ),
    ));

    _lastChunkAt = DateTime.now();
    _micRateWindowStart = DateTime.now();
    _micChunkCountWindow = 0;
    _micBytesWindow = 0;
    debugPrint('[MIC-DEBUG] startStream OK @ ${DateTime.now().toIso8601String()}');
    _recordSub = stream.listen(
      (data) {
        _lastChunkAt = DateTime.now();
        _micChunkCountWindow++;
        _micBytesWindow += data.length;
        _micTotalChunks++;
        _micTotalSamples += data.length ~/ 2;  // PCM16
        final elapsedMs = DateTime.now().difference(_micRateWindowStart).inMilliseconds;
        if (elapsedMs >= 1000) {
          final samples = _micBytesWindow ~/ 2;  // PCM16
          final audioMs = samples * 1000 ~/ 16000;
          debugPrint('[MIC-RATE] last ${elapsedMs}ms: $_micChunkCountWindow chunks, '
              '$samples samples (=${audioMs}ms audio) @ ${DateTime.now().toIso8601String()}');
          _micChunkCountWindow = 0;
          _micBytesWindow = 0;
          _micRateWindowStart = DateTime.now();
        }
        _onChunkCb?.call(Uint8List.fromList(data));
      },
      onError: (e) {
        debugPrint('[AudioService] 錄音 stream onError: $e → 嘗試重啟麥克風');
        _restartMic('stream onError');
      },
      onDone: () {
        debugPrint('[AudioService] 錄音 stream onDone → 嘗試重啟麥克風');
        _restartMic('stream onDone');
      },
      cancelOnError: true,
    );
  }

  /// Watchdog：2 秒沒新 chunk → 強制重啟麥克風
  /// （即使 stream 沒拋 onError/onDone，半關閉狀態也能恢復）
  /// 從 5 秒縮到 2 秒：chime 播放後 Android 暫停 AudioRecord callback，
  /// LocalVoiceService.onChimeComplete 會主動觸發 restart，watchdog 為保底
  void _startMicWatchdog() {
    _micWatchdog?.cancel();
    _micWatchdog = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!_recording) return;
      final since = DateTime.now().difference(_lastChunkAt).inMilliseconds;
      if (since >= 2000) {
        debugPrint('[AudioService] watchdog: ${since}ms 無新 audio chunk → 重啟麥克風');
        _restartMic('watchdog ${since}ms no chunk');
      }
    });
  }

  /// 外部主動觸發 mic 重啟（chime 播完後立刻呼叫，不等 watchdog）
  /// audioplayers 播 chime 時 Android AudioFlinger 暫停 voiceRecognition
  /// AudioRecord callback，chime 結束不會自動恢復，需主動 restart。
  Future<void> restartMicNow(String reason) async {
    if (!_recording || _restarting) return;
    debugPrint('[AudioService] restartMicNow: $reason');
    await _restartMic(reason);
  }

  /// chime（LocalVoiceService）播放期間會搶 audio focus 讓 stream player paused，
  /// chime 結束 audio focus 雖然回來但 just_audio 不自動 resume。由 app_provider
  /// 在 LocalVoiceService.onChimeComplete 同步呼叫此方法主動 resume stream。
  void resumeStreamIfPaused() {
    if (!_shouldPlayStream) return;
    if (!_player.playing) {
      debugPrint('[AudioService-STREAM] chime 結束 → 主動 resume stream player @ '
          '${DateTime.now().toIso8601String()}');
      _player.play();
    }
  }

  Future<void> _restartMic(String reason) async {
    if (_restarting || !_recording || _onChunkCb == null) return;
    _restarting = true;
    try {
      try { await _recordSub?.cancel(); } catch (_) {}
      _recordSub = null;
      try { await _recorder.stop(); } catch (_) {}
      await Future.delayed(const Duration(milliseconds: 200));
      await _startInternal();
      debugPrint('[AudioService] 麥克風重啟成功（原因: $reason）');
    } catch (e) {
      debugPrint('[AudioService] 麥克風重啟失敗: $e（原因: $reason）→ 1 秒後重試');
      Future.delayed(const Duration(seconds: 1), () {
        if (_recording) _restartMic('retry after fail: $reason');
      });
    } finally {
      _restarting = false;
    }
  }

  Future<void> stopMicrophone() async {
    _recording = false;
    _onChunkCb = null;
    _micWatchdog?.cancel();
    _micWatchdog = null;
    await _recordSub?.cancel();
    _recordSub = null;
    await _recorder.stop();
  }

  bool get isRecording => _recording;

  // ── TTS 下行播放 ─────────────────────────────────────────────────────────
  // 用 just_audio（Android 內部 ExoPlayer）取代 audioplayers MediaPlayer：
  // audioplayers 6.x 對 chunked HTTP wav stream 的 prepare 階段會卡 30s timeout，
  // ExoPlayer 對串流處理穩定。chime / cached TTS 仍用 audioplayers（短 wav 沒問題）。
  //
  // 三個 audio focus 選項全設 false，徹底避免跟 chime（LocalVoiceService
  // audioplayers）搶 audio focus 造成的循環互砍：
  // - handleInterruptions: false → 被其他 player 搶 focus 時不自動 pause
  // - androidApplyAudioAttributes: false → ExoPlayer 不設 AudioAttributes，不
  //   申請 AudioFocusRequest，不會壓制 mic 的 voiceRecognition AudioRecord
  // - handleAudioSessionActivation: false → 不啟動 audio session（iOS 主要影響）
  final ja.AudioPlayer _player = ja.AudioPlayer(
    handleInterruptions: false,
    androidApplyAudioAttributes: false,
    handleAudioSessionActivation: false,
  );
  bool _wasStreamPlaying = false;  // 上次 state 的 playing 值（保留作為防禦性 log，
                                    // 預期 handleInterruptions=false 後不再被 pause）

  Future<void> playStreamWav(String host, int port,
      {bool secure = false, String? baseUrl}) async {
    final url = AppConstants.streamWav(host, port,
        secure: secure, baseUrl: baseUrl);
    _streamUrl = url;
    _shouldPlayStream = true;

    await _player.setVolume(1.0);

    // 取消舊的狀態監聽，重新設置
    await _playerStateSub?.cancel();
    _wasStreamPlaying = false;
    _playerStateSub = _player.playerStateStream.listen((state) {
      debugPrint('[AudioService-STREAM] state @ ${DateTime.now().toIso8601String()}: '
          'processing=${state.processingState}, playing=${state.playing}');
      // 只在 completed 時重連（idle/loading/buffering/ready 都不重連）
      if (_shouldPlayStream && state.processingState == ja.ProcessingState.completed) {
        debugPrint('[AudioService-STREAM] completed → schedule reconnect');
        _scheduleReconnect();
      }
      // Audio focus 自動恢復：chime（LocalVoiceService audioplayers）播放時會搶
      // audio focus → ExoPlayer 自動 pause stream（playing=false）；chime 結束後
      // audio focus 雖然回來但 just_audio 不自動 resume → server 推 PCM 都白費。
      // 在這裡偵測「之前在 playing 但現在 paused 且仍 ready」→ 主動 play()。
      if (_shouldPlayStream &&
          state.processingState == ja.ProcessingState.ready &&
          _wasStreamPlaying && !state.playing) {
        debugPrint('[AudioService-STREAM] 偵測到從 playing 變 paused（audio focus loss）→ 主動 resume');
        _player.play();
      }
      _wasStreamPlaying = state.playing;
    });

    debugPrint('[AudioService-STREAM] 連線 /stream.wav: $url @ ${DateTime.now().toIso8601String()}');
    try {
      // just_audio: setUrl 觸發 prepare（ExoPlayer 處理 chunked stream 不會卡），
      // play() 開始播放（non-blocking，不等 stream 結束）
      await _player.setUrl(url);
      debugPrint('[AudioService-STREAM] setUrl() returned @ ${DateTime.now().toIso8601String()}');
      _player.play();   // 不 await，play 觸發後立即返回
      debugPrint('[AudioService-STREAM] play() called @ ${DateTime.now().toIso8601String()}');
    } catch (e) {
      debugPrint('[AudioService-STREAM] 連線失敗: $e');
      _scheduleReconnect();
    }
  }

  /// 延遲後重新連線 /stream.wav（伺服器可能因重置而切斷連線）
  void _scheduleReconnect() {
    // 防止多個重連同時觸發（racing condition 保護）
    if (!_shouldPlayStream || _streamUrl == null || _isReconnecting) return;
    _isReconnecting = true;
    final scheduledAt = DateTime.now();
    debugPrint('[AudioService-STREAM] _scheduleReconnect 觸發 @ ${scheduledAt.toIso8601String()}');
    Future.delayed(const Duration(milliseconds: 800), () async {
      if (!_shouldPlayStream || _streamUrl == null) {
        _isReconnecting = false;
        return;
      }
      debugPrint('[AudioService-STREAM] 重連 /stream.wav... @ ${DateTime.now().toIso8601String()}');
      try {
        // 先確保播放器處於乾淨狀態再設定新來源
        await _player.stop();
        await Future.delayed(const Duration(milliseconds: 100));
        await _player.setUrl(_streamUrl!);
        _player.play();
        debugPrint('[AudioService-STREAM] 重連成功 @ ${DateTime.now().toIso8601String()}（耗時 ${DateTime.now().difference(scheduledAt).inMilliseconds}ms）');
      } catch (e) {
        debugPrint('[AudioService-STREAM] 重連失敗 @ ${DateTime.now().toIso8601String()}: $e（耗時 ${DateTime.now().difference(scheduledAt).inMilliseconds}ms）');
        _isReconnecting = false;
        // 連線失敗，2 秒後再試（加長間隔避免短時間狂打 server）
        Future.delayed(const Duration(seconds: 2), _scheduleReconnect);
        return;
      }
      _isReconnecting = false;
    });
  }

  Future<void> stopPlayback() async {
    _shouldPlayStream = false;
    _isReconnecting   = false;
    _streamUrl = null;
    await _playerStateSub?.cancel();
    _playerStateSub = null;
    await _player.stop();
  }

  /// 本地語音播放時，將 /stream.wav 靜音 [durationMs] 毫秒以避免重疊
  /// 本地播完後自動恢復音量
  Future<void> suppressStreamFor(int durationMs) async {
    await _player.setVolume(0.0);
    await Future.delayed(Duration(milliseconds: durationMs + 200)); // 多200ms緩衝
    if (_shouldPlayStream) {
      await _player.setVolume(1.0);
    }
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
    _isReconnecting   = false;
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
