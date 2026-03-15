import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme.dart';
import '../../data/services/audio_service.dart';

/// Voice input button with push-to-talk functionality.
class VoiceInput extends ConsumerStatefulWidget {
  const VoiceInput({super.key});

  @override
  ConsumerState<VoiceInput> createState() => _VoiceInputState();
}

class _VoiceInputState extends ConsumerState<VoiceInput> {
  bool _isPressed = false;

  @override
  Widget build(BuildContext context) {
    final audioService = ref.watch(audioServiceProvider);
    final statusAsync = ref.watch(audioStatusProvider);
    final isPlayingAsync = ref.watch(isPlayingProvider);

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        // Status display
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(
            color: AppTheme.surfaceColor,
            borderRadius: BorderRadius.circular(8),
          ),
          child: statusAsync.when(
            data: (status) => Text(
              status,
              style: const TextStyle(
                color: AppTheme.textPrimary,
                fontSize: 14,
              ),
              textAlign: TextAlign.center,
            ),
            loading: () => const Text(
              'Ready',
              style: TextStyle(color: AppTheme.textSecondary),
            ),
            error: (_, __) => const Text(
              'Error',
              style: TextStyle(color: AppTheme.errorColor),
            ),
          ),
        ),

        const SizedBox(height: 16),

        // Microphone button
        GestureDetector(
          onLongPressStart: (_) => _startRecording(audioService),
          onLongPressEnd: (_) => _stopRecording(audioService),
          child: Container(
            width: 120,
            height: 120,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: _isPressed ? AppTheme.errorColor : AppTheme.primaryColor,
              boxShadow: [
                BoxShadow(
                  color: (_isPressed ? AppTheme.errorColor : AppTheme.primaryColor)
                      .withOpacity(0.4),
                  blurRadius: _isPressed ? 30 : 20,
                  spreadRadius: _isPressed ? 5 : 0,
                ),
              ],
            ),
            child: Icon(
              _isPressed ? Icons.mic : Icons.mic_none,
              size: 48,
              color: AppTheme.textPrimary,
            ),
          ),
        ),

        const SizedBox(height: 12),

        // Instructions
        Text(
          _isPressed ? 'Release to send' : 'Hold to speak',
          style: TextStyle(
            color: _isPressed ? AppTheme.errorColor : AppTheme.textSecondary,
            fontSize: 14,
          ),
        ),

        // Stop playback button
        if (isPlayingAsync.when(
          data: (isPlaying) => isPlaying,
          loading: () => false,
          error: (_, __) => false,
        ))
          Padding(
            padding: const EdgeInsets.only(top: 16),
            child: TextButton.icon(
              onPressed: () => audioService.stopPlayback(),
              icon: const Icon(Icons.stop),
              label: const Text('Stop'),
              style: TextButton.styleFrom(
                foregroundColor: AppTheme.warningColor,
              ),
            ),
          ),
      ],
    );
  }

  void _startRecording(AudioService audioService) {
    setState(() => _isPressed = true);
    audioService.startRecording();
  }

  void _stopRecording(AudioService audioService) {
    setState(() => _isPressed = false);
    audioService.stopRecording();
  }
}
