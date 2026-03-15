import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme.dart';
import '../../data/services/audio_service.dart';
import '../../data/services/websocket_service.dart';

/// Chat panel showing conversation history.
class ChatPanel extends ConsumerStatefulWidget {
  const ChatPanel({super.key});

  @override
  ConsumerState<ChatPanel> createState() => _ChatPanelState();
}

class _ChatPanelState extends ConsumerState<ChatPanel> {
  final List<ChatMessage> _messages = [];
  StreamSubscription<String>? _transcriptSubscription;

  @override
  void initState() {
    super.initState();
    _listenToTranscripts();
  }

  @override
  void dispose() {
    _transcriptSubscription?.cancel();
    super.dispose();
  }

  void _listenToTranscripts() {
    final wsService = ref.read(webSocketServiceProvider);
    _transcriptSubscription = wsService.transcripts.listen((transcript) {
      if (transcript.isNotEmpty) {
        setState(() {
          _messages.add(ChatMessage(
            text: transcript,
            isUser: false,
            timestamp: DateTime.now(),
          ));
        });
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final statusAsync = ref.watch(audioStatusProvider);

    return Container(
      decoration: BoxDecoration(
        color: AppTheme.surfaceColor,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          // Header
          Container(
            padding: const EdgeInsets.all(12),
            decoration: const BoxDecoration(
              border: Border(
                bottom: BorderSide(color: AppTheme.cardColor),
              ),
            ),
            child: Row(
              children: [
                const Icon(
                  Icons.chat,
                  color: AppTheme.primaryColor,
                  size: 20,
                ),
                const SizedBox(width: 8),
                const Text(
                  'Conversation',
                  style: TextStyle(
                    color: AppTheme.textPrimary,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const Spacer(),
                if (_messages.isNotEmpty)
                  TextButton(
                    onPressed: () {
                      setState(() => _messages.clear());
                    },
                    child: const Text(
                      'Clear',
                      style: TextStyle(fontSize: 12),
                    ),
                  ),
              ],
            ),
          ),

          // Messages
          Expanded(
            child: _messages.isEmpty
                ? const Center(
                    child: Text(
                      'Start a conversation...',
                      style: TextStyle(
                        color: AppTheme.textSecondary,
                        fontSize: 14,
                      ),
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.all(8),
                    itemCount: _messages.length,
                    itemBuilder: (context, index) {
                      final msg = _messages[index];
                      return _MessageBubble(message: msg);
                    },
                  ),
          ),

          // Current status
          Container(
            padding: const EdgeInsets.all(8),
            child: statusAsync.when(
              data: (status) => Text(
                status,
                style: const TextStyle(
                  color: AppTheme.textSecondary,
                  fontSize: 12,
                ),
                textAlign: TextAlign.center,
              ),
              loading: () => const SizedBox.shrink(),
              error: (_, __) => const SizedBox.shrink(),
            ),
          ),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  final ChatMessage message;

  const _MessageBubble({required this.message});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: message.isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: message.isUser
              ? AppTheme.primaryColor
              : AppTheme.cardColor,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              message.text,
              style: const TextStyle(
                color: AppTheme.textPrimary,
                fontSize: 14,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              _formatTime(message.timestamp),
              style: const TextStyle(
                color: AppTheme.textSecondary,
                fontSize: 10,
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _formatTime(DateTime time) {
    return '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';
  }
}

class ChatMessage {
  final String text;
  final bool isUser;
  final DateTime timestamp;

  ChatMessage({
    required this.text,
    required this.isUser,
    required this.timestamp,
  });
}
