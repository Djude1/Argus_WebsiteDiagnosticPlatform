import 'package:freezed_annotation/freezed_annotation.dart';

part 'server_config.freezed.dart';

/// Server connection configuration.
@freezed
class ServerConfig with _$ServerConfig {
  const factory ServerConfig({
    @Default('192.168.1.100') String serverIp,
    @Default(8081) int serverPort,
    @Default(false) bool autoConnect,
  }) = _ServerConfig;
}

/// Connection status enum.
enum ConnectionStatus {
  disconnected,
  connecting,
  connected,
  reconnecting,
  error,
}

/// Extension for connection status display.
extension ConnectionStatusExtension on ConnectionStatus {
  String get displayName {
    switch (this) {
      case ConnectionStatus.disconnected:
        return 'Disconnected';
      case ConnectionStatus.connecting:
        return 'Connecting...';
      case ConnectionStatus.connected:
        return 'Connected';
      case ConnectionStatus.reconnecting:
        return 'Reconnecting...';
      case ConnectionStatus.error:
        return 'Error';
    }
  }
}
