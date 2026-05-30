import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/constants.dart';
import '../../core/theme.dart';
import '../../data/models/server_config.dart';
import '../../data/services/websocket_service.dart';

/// Server settings provider.
final serverConfigProvider =
    StateNotifierProvider<ServerConfigNotifier, ServerConfig>((ref) {
  return ServerConfigNotifier();
});

class ServerConfigNotifier extends StateNotifier<ServerConfig> {
  ServerConfigNotifier() : super(const ServerConfig()) {
    _loadConfig();
  }

  Future<void> _loadConfig() async {
    final prefs = await SharedPreferences.getInstance();
    state = ServerConfig(
      serverIp: prefs.getString('server_ip') ?? AppConstants.defaultServerIp,
      serverPort: prefs.getInt('server_port') ?? AppConstants.defaultServerPort,
      autoConnect: prefs.getBool('auto_connect') ?? false,
    );
  }

  Future<void> updateConfig(ServerConfig config) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('server_ip', config.serverIp);
    await prefs.setInt('server_port', config.serverPort);
    await prefs.setBool('auto_connect', config.autoConnect);
    state = config;
  }
}

/// Server settings page.
class ServerSettingsPage extends ConsumerStatefulWidget {
  const ServerSettingsPage({super.key});

  @override
  ConsumerState<ServerSettingsPage> createState() => _ServerSettingsPageState();
}

class _ServerSettingsPageState extends ConsumerState<ServerSettingsPage> {
  final _formKey = GlobalKey<FormState>();
  late TextEditingController _ipController;
  late TextEditingController _portController;
  bool _autoConnect = false;

  @override
  void initState() {
    super.initState();
    final config = ref.read(serverConfigProvider);
    _ipController = TextEditingController(text: config.serverIp);
    _portController = TextEditingController(text: config.serverPort.toString());
    _autoConnect = config.autoConnect;
  }

  @override
  void dispose() {
    _ipController.dispose();
    _portController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final config = ref.watch(serverConfigProvider);
    final connectionStatus = ref.watch(connectionStatusProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Server Settings'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Server IP
              TextFormField(
                controller: _ipController,
                decoration: const InputDecoration(
                  labelText: 'Server IP',
                  hintText: 'e.g., 192.168.1.100',
                  prefixIcon: Icon(Icons.dns),
                ),
                keyboardType: TextInputType.text,
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return 'Please enter server IP';
                  }
                  return null;
                },
              ),

              const SizedBox(height: 16),

              // Server Port
              TextFormField(
                controller: _portController,
                decoration: const InputDecoration(
                  labelText: 'Port',
                  hintText: 'e.g., 8081',
                  prefixIcon: Icon(Icons.numbers),
                ),
                keyboardType: TextInputType.number,
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return 'Please enter port';
                  }
                  final port = int.tryParse(value);
                  if (port == null || port < 1 || port > 65535) {
                    return 'Please enter a valid port (1-65535)';
                  }
                  return null;
                },
              ),

              const SizedBox(height: 16),

              // Auto-connect toggle
              SwitchListTile(
                title: const Text('Auto-connect on startup'),
                subtitle: const Text(
                  'Automatically connect when app starts',
                  style: TextStyle(fontSize: 12),
                ),
                value: _autoConnect,
                onChanged: (value) {
                  setState(() => _autoConnect = value);
                },
              ),

              const SizedBox(height: 24),

              // Connection status
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: AppTheme.surfaceColor,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  children: [
                    Icon(
                      _getStatusIcon(connectionStatus),
                      color: _getStatusColor(connectionStatus),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Connection Status',
                            style: TextStyle(
                              color: AppTheme.textSecondary,
                              fontSize: 12,
                            ),
                          ),
                          Text(
                            connectionStatus.when(
                              data: (status) => status.displayName,
                              loading: () => 'Checking...',
                              error: (_, __) => 'Error',
                            ),
                            style: TextStyle(
                              color: _getStatusColor(connectionStatus),
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 24),

              // Save button
              ElevatedButton(
                onPressed: _saveConfig,
                child: const Text('Save Settings'),
              ),

              const SizedBox(height: 12),

              // Test connection button
              OutlinedButton(
                onPressed: _testConnection,
                child: const Text('Test Connection'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  IconData _getStatusIcon(AsyncValue<ConnectionStatus> status) {
    return status.when(
      data: (s) => switch (s) {
        ConnectionStatus.connected => Icons.check_circle,
        ConnectionStatus.connecting => Icons.pending,
        ConnectionStatus.reconnecting => Icons.refresh,
        ConnectionStatus.disconnected => Icons.cancel_outlined,
        ConnectionStatus.error => Icons.error,
      },
      loading: () => Icons.pending,
      error: (_, __) => Icons.error,
    );
  }

  Color _getStatusColor(AsyncValue<ConnectionStatus> status) {
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

  Future<void> _saveConfig() async {
    if (!_formKey.currentState!.validate()) return;

    final newConfig = ServerConfig(
      serverIp: _ipController.text.trim(),
      serverPort: int.parse(_portController.text),
      autoConnect: _autoConnect,
    );

    await ref.read(serverConfigProvider.notifier).updateConfig(newConfig);

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Settings saved')),
      );
    }
  }

  Future<void> _testConnection() async {
    if (!_formKey.currentState!.validate()) return;

    // Update config first
    await _saveConfig();

    // Get WebSocket service and connect
    final wsService = ref.read(webSocketServiceProvider);
    final config = ref.read(serverConfigProvider);
    wsService.updateConfig(config);
    await wsService.connect();

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Testing connection...')),
      );
    }
  }
}
