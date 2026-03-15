import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:logger/logger.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:uuid/uuid.dart';

import '../../core/constants.dart';
import 'websocket_service.dart';

/// Audio service for recording and playback.
class AudioService {
  final Logger _logger = Logger();
  final WebSocketService _wsService;
  final Uuid _uuid = const Uuid();

  final AudioRecorder _recorder = AudioRecorder();
  final AudioPlayer _player = AudioPlayer();

  bool _isRecording = false;
  bool _isPlaying = false;
  String? _currentRecordingPath;

  final StreamController<bool> _recordingStateController =
      StreamController<bool>.broadcast();
  final StreamController<bool> _playingStateController =
      StreamController<bool>.broadcast();
  final StreamController<String> _statusController =
      StreamController<String>.broadcast();

  Stream<bool> get recordingState => _recordingStateController.stream;
  Stream<bool> get playingState => _playingStateController.stream;
  Stream<String> get status => _statusController.stream;
  bool get isRecording => _isRecording;
  bool get isPlaying => _isPlaying;

  AudioService(this._wsService) {
    _setupAudioPlayer();
    _listenToAudioResponses();
  }

  void _setupAudioPlayer() {
    _player.onPlayerComplete.listen((_) {
      _isPlaying = false;
      _playingStateController.add(false);
      _statusController.add('Ready');
    });

    _player.onLog.listen((msg) {
      _logger.d('AudioPlayer: $msg');
    });
  }

  void _listenToAudioResponses() {
    _wsService.audioResponses.listen((audioData) {
      _playAudio(audioData);
    });

    _wsService.transcripts.listen((transcript) {
      _statusController.add('AI: $transcript');
    });
  }

  /// Check and request microphone permission.
  Future<bool> checkPermission() async {
    return await _recorder.hasPermission();
  }

  /// Start recording audio.
  Future<void> startRecording() async {
    if (_isRecording) return;

    final hasPermission = await checkPermission();
    if (!hasPermission) {
      _logger.e('Microphone permission not granted');
      _statusController.add('Permission denied');
      return;
    }

    // Create temp file for recording
    final tempDir = await getTemporaryDirectory();
    _currentRecordingPath = '${tempDir.path}/recording_${_uuid.v4()}.wav';

    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.wav,
        sampleRate: AppConstants.audioSampleRate,
        numChannels: AppConstants.audioChannels,
      ),
      path: _currentRecordingPath!,
    );

    _isRecording = true;
    _recordingStateController.add(true);
    _statusController.add('Recording...');
    _logger.i('Started recording');
  }

  /// Stop recording and send audio to server.
  Future<void> stopRecording() async {
    if (!_isRecording) return;

    final audioPath = await _recorder.stop();
    _isRecording = false;
    _recordingStateController.add(false);

    if (audioPath != null) {
      _statusController.add('Processing...');
      _logger.i('Recording saved to $audioPath');

      // Read and send the audio file to server
      try {
        final file = File(audioPath);
        final bytes = await file.readAsBytes();
        _wsService.sendAudioData(bytes);
        _logger.i('Sent ${bytes.length} bytes to server');

        // Clean up temp file
        await file.delete();
      } catch (e) {
        _logger.e('Failed to send audio: $e');
      }
    }
  }

  /// Stream audio data directly to server.
  void sendAudioChunk(Uint8List audioData) {
    _wsService.sendAudioData(audioData);
  }

  /// Play audio from bytes.
  Future<void> _playAudio(Uint8List audioData) async {
    if (_isPlaying) {
      await _player.stop();
    }

    _isPlaying = true;
    _playingStateController.add(true);
    _statusController.add('Playing response...');

    await _player.play(BytesSource(audioData));
    _logger.i('Playing audio response');
  }

  /// Stop playback.
  Future<void> stopPlayback() async {
    await _player.stop();
    _isPlaying = false;
    _playingStateController.add(false);
    _statusController.add('Ready');
  }

  /// Dispose resources.
  Future<void> dispose() async {
    await _recorder.stop();
    await _recorder.dispose();
    await _player.dispose();
    _recordingStateController.close();
    _playingStateController.close();
    _statusController.close();
  }
}

/// Provider for audio service.
final audioServiceProvider = Provider<AudioService>((ref) {
  final wsService = ref.watch(webSocketServiceProvider);
  final service = AudioService(wsService);
  ref.onDispose(() => service.dispose());
  return service;
});

/// Provider for recording state.
final isRecordingProvider = StreamProvider<bool>((ref) {
  final service = ref.watch(audioServiceProvider);
  return service.recordingState;
});

/// Provider for playing state.
final isPlayingProvider = StreamProvider<bool>((ref) {
  final service = ref.watch(audioServiceProvider);
  return service.playingState;
});

/// Provider for audio status.
final audioStatusProvider = StreamProvider<String>((ref) {
  final service = ref.watch(audioServiceProvider);
  return service.status;
});
