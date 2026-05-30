import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:permission_handler/permission_handler.dart';

import '../core/theme.dart';
import '../data/services/audio_service.dart';
import '../data/services/camera_stream_service.dart';
import '../data/services/websocket_service.dart';
import '../data/models/server_config.dart';
import '../features/camera/camera_controller.dart';
import '../features/camera/camera_viewer.dart';
import '../features/voice/voice_input.dart';
import '../features/voice/voice_output.dart';
import '../features/settings/server_settings.dart';

/// Main page combining camera and voice features.
class MainPage extends ConsumerStatefulWidget {
  const MainPage({super.key});

  @override
  ConsumerState<MainPage> createState() => _MainPageState();
}

class _MainPageState extends ConsumerState<MainPage>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  bool _permissionsGranted = false;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _requestPermissions();
    _initializeServices();
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  Future<void> _requestPermissions() async {
    final cameraStatus = await Permission.camera.request();
    final micStatus = await Permission.microphone.request();

    setState(() {
      _permissionsGranted =
          cameraStatus.isGranted && micStatus.isGranted;
    });

    if (!_permissionsGranted && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Camera and microphone permissions are required'),
          backgroundColor: AppTheme.errorColor,
        ),
      );
    }
  }

  Future<void> _initializeServices() async {
    // Initialize camera
    await ref.read(cameraNotifierProvider.notifier).initialize();

    // Connect to server if auto-connect is enabled
    final config = ref.read(serverConfigProvider);
    if (config.autoConnect) {
      final wsService = ref.read(webSocketServiceProvider);
      wsService.updateConfig(config);
      await wsService.connect();
    }
  }

  @override
  Widget build(BuildContext context) {
    final connectionStatus = ref.watch(connectionStatusProvider);
    final cameraState = ref.watch(cameraNotifierProvider);

    return Scaffold(
      body: Column(
        children: [
          // Connection status bar
          _buildStatusBar(connectionStatus),

          // Main content
          Expanded(
            child: TabBarView(
              controller: _tabController,
              children: [
                // Camera tab
                _buildCameraTab(cameraState),

                // Voice tab
                _buildVoiceTab(),
              ],
            ),
          ),
        ],
      ),

      // Bottom navigation
      bottomNavigationBar: _buildBottomNav(),
    );
  }

  Widget _buildStatusBar(AsyncValue<ConnectionStatus> status) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: const BoxDecoration(
        color: AppTheme.surfaceColor,
        boxShadow: [
          BoxShadow(
            color: Colors.black12,
            blurRadius: 4,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: SafeArea(
        bottom: false,
        child: Row(
          children: [
            Icon(
              _getConnectionIcon(status),
              color: _getConnectionColor(status),
              size: 16,
            ),
            const SizedBox(width: 8),
            Text(
              status.when(
                data: (s) => s.displayName,
                loading: () => 'Checking...',
                error: (_, __) => 'Error',
              ),
              style: const TextStyle(
                color: AppTheme.textPrimary,
                fontSize: 12,
              ),
            ),
            const Spacer(),
            if (!_permissionsGranted)
              TextButton(
                onPressed: _requestPermissions,
                child: const Text(
                  'Grant Permissions',
                  style: TextStyle(fontSize: 12),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildCameraTab(AsyncValue<bool> cameraState) {
    return cameraState.when(
      loading: () => const Center(
        child: CircularProgressIndicator(),
      ),
      error: (err, _) => Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              Icons.error_outline,
              size: 48,
              color: AppTheme.errorColor,
            ),
            const SizedBox(height: 16),
            Text(
              'Camera error: $err',
              style: const TextStyle(color: AppTheme.errorColor),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () {
                ref.read(cameraNotifierProvider.notifier).initialize();
              },
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
      data: (_) => Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            // Camera viewer
            const Expanded(child: CameraViewer()),

            const SizedBox(height: 16),

            // Camera controls
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                _ControlButton(
                  icon: Icons.videocam,
                  label: 'Start Stream',
                  onPressed: () {
                    ref.read(cameraNotifierProvider.notifier).startStreaming();
                  },
                ),
                _ControlButton(
                  icon: Icons.videocam_off,
                  label: 'Stop Stream',
                  onPressed: () {
                    ref.read(cameraNotifierProvider.notifier).stopStreaming();
                  },
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildVoiceTab() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          // Chat panel
          const Expanded(child: ChatPanel()),

          const SizedBox(height: 16),

          // Voice input
          const VoiceInput(),
        ],
      ),
    );
  }

  Widget _buildBottomNav() {
    return Container(
      decoration: const BoxDecoration(
        color: AppTheme.surfaceColor,
        boxShadow: [
          BoxShadow(
            color: Colors.black12,
            blurRadius: 4,
            offset: Offset(0, -2),
          ),
        ],
      ),
      child: SafeArea(
        top: false,
        child: TabBar(
          controller: _tabController,
          indicatorColor: AppTheme.primaryColor,
          labelColor: AppTheme.primaryColor,
          unselectedLabelColor: AppTheme.textSecondary,
          tabs: const [
            Tab(icon: Icon(Icons.camera_alt), text: 'Camera'),
            Tab(icon: Icon(Icons.mic), text: 'Voice'),
          ],
        ),
      ),
    );
  }

  IconData _getConnectionIcon(AsyncValue<ConnectionStatus> status) {
    return status.when(
      data: (s) => switch (s) {
        ConnectionStatus.connected => Icons.wifi,
        ConnectionStatus.connecting => Icons.wifi_lock,
        ConnectionStatus.reconnecting => Icons.refresh,
        ConnectionStatus.disconnected => Icons.wifi_off,
        ConnectionStatus.error => Icons.error_outline,
      },
      loading: () => Icons.pending,
      error: (_, __) => Icons.error_outline,
    );
  }

  Color _getConnectionColor(AsyncValue<ConnectionStatus> status) {
    return status.when(
      data: (s) => switch (s) {
        ConnectionStatus.connected => AppTheme.successColor,
        ConnectionStatus.connecting => AppTheme.warningColor,
        ConnectionStatus.reconnecting => AppTheme.warningColor,
        ConnectionStatus.disconnected => AppTheme.textSecondary,
        ConnectionStatus.error => AppTheme.errorColor,
      },
      loading: () => AppTheme.warningColor,
      error: (_, __) => AppTheme.errorColor,
    );
  }
}

class _ControlButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onPressed;

  const _ControlButton({
    required this.icon,
    required this.label,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return ElevatedButton.icon(
      onPressed: onPressed,
      icon: Icon(icon, size: 20),
      label: Text(label),
      style: ElevatedButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      ),
    );
  }
}
