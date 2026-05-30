/// Application constants for API endpoints and default values.
class AppConstants {
  AppConstants._();

  // Default server configuration
  static const String defaultServerIp = '192.168.1.100';
  static const int defaultServerPort = 8000;

  // WebSocket endpoints
  static String cameraWsPath(String ip, int port) =>
      'ws://$ip:$port/ws/camera';
  static String viewerWsPath(String ip, int port) =>
      'ws://$ip:$port/ws/viewer';
  static String audioWsPath(String ip, int port) =>
      'ws://$ip:$port/ws_audio';

  // Camera settings
  static const int cameraFps = 24;
  static const int jpegQuality = 85;
  static const int maxFrameWidth = 640;
  static const int maxFrameHeight = 480;

  // Audio settings
  static const int audioSampleRate = 16000;
  static const int audioChannels = 1;
  static const int audioBitDepth = 16;

  // Connection settings
  static const Duration connectionTimeout = Duration(seconds: 10);
  static const Duration reconnectDelay = Duration(seconds: 3);
  static const int maxReconnectAttempts = 3;
  static const Duration heartbeatInterval = Duration(seconds: 30);
}
