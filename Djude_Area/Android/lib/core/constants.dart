// lib/core/constants.dart
// 全域常數：端點 URL、預設值

class AppConstants {
  // ── 伺服器預設值 ────────────────────────────────────────────────────────
  static const String defaultHost   = '10.0.2.2';
  static const int    defaultPort   = 8081;
  static const bool   defaultSecure = false; // true = wss:// / https://

  // ── 協定選擇（區網用 http/ws，公網用 https/wss）──────────────────────────
  static String httpScheme(bool secure) => secure ? 'https' : 'http';
  static String wsScheme  (bool secure) => secure ? 'wss'   : 'ws';

  // ── HTTP API ─────────────────────────────────────────────────────────────
  static String httpBase(String host, int port, {bool secure = false}) =>
      '${httpScheme(secure)}://$host:$port';

  static String apiLogin(String host, int port, {bool secure = false}) =>
      '${httpBase(host, port, secure: secure)}/api/login';
  static String apiMe(String host, int port, {bool secure = false}) =>
      '${httpBase(host, port, secure: secure)}/api/me';
  static String apiUsers(String host, int port, {bool secure = false}) =>
      '${httpBase(host, port, secure: secure)}/api/users';
  static String apiContacts(String host, int port, {bool secure = false}) =>
      '${httpBase(host, port, secure: secure)}/api/contacts';
  static String apiNavState(String host, int port, {bool secure = false}) =>
      '${httpBase(host, port, secure: secure)}/api/nav/state';
  static String apiNavBlindpath(String host, int port, {bool secure = false}) =>
      '${httpBase(host, port, secure: secure)}/api/nav/blindpath';
  static String apiNavCrossing(String host, int port, {bool secure = false}) =>
      '${httpBase(host, port, secure: secure)}/api/nav/crossing';
  static String apiNavTrafficLight(String host, int port, {bool secure = false}) =>
      '${httpBase(host, port, secure: secure)}/api/nav/traffic_light';
  static String apiNavItemSearch(String host, int port, {bool secure = false}) =>
      '${httpBase(host, port, secure: secure)}/api/nav/item_search';
  static String apiNavStop(String host, int port, {bool secure = false}) =>
      '${httpBase(host, port, secure: secure)}/api/nav/stop';

  // ── WebSocket ────────────────────────────────────────────────────────────
  static String wsCamera(String host, int port, {bool secure = false}) =>
      '${wsScheme(secure)}://$host:$port/ws/camera';
  static String wsAudio(String host, int port, {bool secure = false}) =>
      '${wsScheme(secure)}://$host:$port/ws_audio';
  static String wsUi(String host, int port, {bool secure = false}) =>
      '${wsScheme(secure)}://$host:$port/ws_ui';
  static String wsImu(String host, int port, {bool secure = false}) =>
      '${wsScheme(secure)}://$host:$port/ws';

  // AR 視覺化畫面（接收 YOLO 處理後的 JPEG）
  static String wsViewer(String host, int port, {bool secure = false}) =>
      '${wsScheme(secure)}://$host:$port/ws/viewer';

  // ── 音訊下行（TTS）─────────────────────────────────────────────────────
  static String streamWav(String host, int port, {bool secure = false}) =>
      '${httpScheme(secure)}://$host:$port/stream.wav';

  // ── SharedPreferences Keys ───────────────────────────────────────────────
  static const String keySecure = 'server_secure';

  // ── SharedPreferences Keys ───────────────────────────────────────────────
  static const String keyHost = 'server_host';
  static const String keyPort = 'server_port';

  // ── SecureStorage Keys ───────────────────────────────────────────────────
  static const String keyToken    = 'jwt_token';
  static const String keyUsername = 'username';
  static const String keyRole     = 'role';
  static const String keyUserId   = 'user_id';

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
