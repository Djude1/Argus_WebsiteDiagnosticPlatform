import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme.dart';
import '../../data/services/camera_stream_service.dart';
import '../../data/services/websocket_service.dart';

/// Camera viewer widget displaying live annotated frames from server.
class CameraViewer extends ConsumerWidget {
  const CameraViewer({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final frameAsync = ref.watch(viewerFramesProvider);
    final isStreaming = ref.watch(isStreamingProvider);
    final fpsAsync = ref.watch(cameraFpsProvider);
    final latencyAsync = ref.watch(cameraLatencyProvider);

    return Column(
      children: [
        // Main video display
        Expanded(
          child: Container(
            decoration: BoxDecoration(
              color: AppTheme.surfaceColor,
              borderRadius: BorderRadius.circular(12),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: frameAsync.when(
                data: (frameData) => Image.memory(
                  frameData,
                  fit: BoxFit.contain,
                  gaplessPlayback: true,
                ),
                loading: () => const Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.videocam_off,
                        size: 64,
                        color: AppTheme.textSecondary,
                      ),
                      SizedBox(height: 16),
                      Text(
                        'Waiting for video stream...',
                        style: TextStyle(
                          color: AppTheme.textSecondary,
                          fontSize: 16,
                        ),
                      ),
                    ],
                  ),
                ),
                error: (err, stack) => Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(
                        Icons.error_outline,
                        size: 64,
                        color: AppTheme.errorColor,
                      ),
                      const SizedBox(height: 16),
                      Text(
                        'Stream error: $err',
                        style: const TextStyle(
                          color: AppTheme.errorColor,
                          fontSize: 14,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),

        const SizedBox(height: 8),

        // Status bar
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: AppTheme.surfaceColor,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              // FPS
              _StatusItem(
                icon: Icons.speed,
                label: 'FPS',
                value: fpsAsync.when(
                  data: (fps) => '$fps',
                  loading: () => '--',
                  error: (_, __) => '--',
                ),
              ),

              // Latency
              _StatusItem(
                icon: Icons.timer,
                label: 'Latency',
                value: latencyAsync.when(
                  data: (ms) => '${ms}ms',
                  loading: () => '--',
                  error: (_, __) => '--',
                ),
              ),

              // Streaming status
              _StatusItem(
                icon: isStreaming ? Icons.circle : Icons.circle_outlined,
                label: 'Status',
                value: isStreaming ? 'Live' : 'Off',
                color: isStreaming ? AppTheme.successColor : AppTheme.textSecondary,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _StatusItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color? color;

  const _StatusItem({
    required this.icon,
    required this.label,
    required this.value,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 16, color: color ?? AppTheme.textSecondary),
        const SizedBox(width: 4),
        Text(
          '$label: $value',
          style: TextStyle(
            color: color ?? AppTheme.textPrimary,
            fontSize: 12,
          ),
        ),
      ],
    );
  }
}
