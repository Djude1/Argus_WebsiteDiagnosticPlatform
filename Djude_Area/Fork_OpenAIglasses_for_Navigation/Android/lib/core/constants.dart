// lib/core/constants.dart
// 全域常數：端點 URL、預設值

class AppConstants {
  // ── 伺服器預設值 ────────────────────────────────────────────────────────
  static const String defaultHost   = '10.0.2.2';
  static const int    defaultPort   = 8081;
  static const bool   defaultSecure = false; // true = wss:// / https://
  static const String defaultBaseUrl = '';  // 空白表示使用 host+port 模式

  // ── 協定選擇（區網用 http/ws，公網用 https/wss）──────────────────────────
  static String httpScheme(bool secure) => secure ? 'https' : 'http';
  static String wsScheme  (bool secure) => secure ? 'wss'   : 'ws';

  // ── URL 解析（支援完整 URL 或 IP:Port）──────────────────────────────────
  /// 判斷是否為完整 URL（含 scheme）
  static bool isFullUrl(String input) {
    return input.startsWith('http://') || input.startsWith('https://');
  }

  /// 解析 URL，回傳 (scheme, host, port, secure)
  static ({String scheme, String host, int port, bool secure}) parseUrl(String baseUrl, {int defaultPort = 8081}) {
    if (isFullUrl(baseUrl)) {
      final uri = Uri.parse(baseUrl);
      return (
        scheme: uri.scheme,
        host: uri.host,
        port: uri.hasPort ? uri.port : (uri.scheme == 'https' ? 443 : 80),
        secure: uri.scheme == 'https',
      );
    } else {
      // 舊式 host:port 格式
      return (scheme: 'http', host: baseUrl, port: defaultPort, secure: false);
    }
  }

  // ── HTTP API ─────────────────────────────────────────────────────────────
  /// 產生 HTTP base URL（支援完整 URL 或 host+port）
  static String httpBase(String host, int port, {bool secure = false, String? baseUrl}) {
    if (baseUrl != null && baseUrl.isNotEmpty && isFullUrl(baseUrl)) {
      // 使用完整 URL，移除結尾斜線
      return baseUrl.replaceAll(RegExp(r'/+$'), '');
    }
    return '${httpScheme(secure)}://$host:$port';
  }

  static String apiNavState(String host, int port, {bool secure = false, String? baseUrl}) =>
      '${httpBase(host, port, secure: secure, baseUrl: baseUrl)}/api/nav/state';
  static String apiNavBlindpath(String host, int port, {bool secure = false, String? baseUrl}) =>
      '${httpBase(host, port, secure: secure, baseUrl: baseUrl)}/api/nav/blindpath';
  static String apiNavCrossing(String host, int port, {bool secure = false, String? baseUrl}) =>
      '${httpBase(host, port, secure: secure, baseUrl: baseUrl)}/api/nav/crossing';
  static String apiNavTrafficLight(String host, int port, {bool secure = false, String? baseUrl}) =>
      '${httpBase(host, port, secure: secure, baseUrl: baseUrl)}/api/nav/traffic_light';
  static String apiNavItemSearch(String host, int port, {bool secure = false, String? baseUrl}) =>
      '${httpBase(host, port, secure: secure, baseUrl: baseUrl)}/api/nav/item_search';
  static String apiNavStop(String host, int port, {bool secure = false, String? baseUrl}) =>
      '${httpBase(host, port, secure: secure, baseUrl: baseUrl)}/api/nav/stop';

  // ── WebSocket ────────────────────────────────────────────────────────────
  static String _wsBase(String host, int port, bool secure, String? baseUrl, String path) {
    if (baseUrl != null && baseUrl.isNotEmpty && isFullUrl(baseUrl)) {
      return '${baseUrl.replaceAll(RegExp(r'/+$'), '').replaceFirst(RegExp(r'^https?'), secure ? 'wss' : 'ws')}$path';
    }
    return '${wsScheme(secure)}://$host:$port$path';
  }

  static String wsCamera(String host, int port, {bool secure = false, String? baseUrl}) =>
      _wsBase(host, port, secure, baseUrl, '/ws/camera');
  static String wsAudio(String host, int port, {bool secure = false, String? baseUrl}) =>
      _wsBase(host, port, secure, baseUrl, '/ws_audio');
  static String wsUi(String host, int port, {bool secure = false, String? baseUrl}) =>
      _wsBase(host, port, secure, baseUrl, '/ws_ui');
  static String wsImu(String host, int port, {bool secure = false, String? baseUrl}) =>
      _wsBase(host, port, secure, baseUrl, '/ws');

  // AR 視覺化畫面（接收 YOLO 處理後的 JPEG）
  static String wsViewer(String host, int port, {bool secure = false, String? baseUrl}) =>
      _wsBase(host, port, secure, baseUrl, '/ws/viewer');

  // ── 音訊下行（TTS）─────────────────────────────────────────────────────
  static String streamWav(String host, int port, {bool secure = false, String? baseUrl}) =>
      '${httpBase(host, port, secure: secure, baseUrl: baseUrl)}/stream.wav';

  // ── SharedPreferences Keys ───────────────────────────────────────────────
  static const String keySecure      = 'server_secure';
  static const String keyHost        = 'server_host';
  static const String keyPort        = 'server_port';
  static const String keyBaseUrl     = 'server_base_url';
  // 配置來源網站 URL（Django Website，用於遠端讀取 AI 伺服器位址）
  static const String keyWebsiteUrl  = 'config_website_url';

  // ── 導航狀態顯示名稱對照 ─────────────────────────────────────────────────
  static const Map<String, String> navStateLabels = {
    'IDLE':                     '待機',
    'CHAT':                     '對話中',
    'BLINDPATH_NAV':            '盲道導航中',
    'CROSSING':                 '過馬路中',
    'SEEKING_CROSSWALK':        '尋找斑馬線',
    'WAIT_TRAFFIC_LIGHT':       '等待綠燈',
    'SEEKING_NEXT_BLINDPATH':   '尋找下一段盲道',
    'ITEM_SEARCH':              '物品尋找中',
    'TRAFFIC_LIGHT_DETECTION':  '紅綠燈偵測中',
    'unavailable':              '伺服器未連線',
  };

  static String stateLabel(String state) =>
      navStateLabels[state] ?? state;
}
