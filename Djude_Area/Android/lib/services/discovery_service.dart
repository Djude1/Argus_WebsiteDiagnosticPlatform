// lib/services/discovery_service.dart
// 自動發現伺服器 IP：監聽 UDP port 47777 的廣播封包
// 伺服器每 2 秒廣播 {"service":"ai_glasses","port":8081}

import 'dart:async';
import 'dart:convert';
import 'dart:io';

class DiscoveryResult {
  final String host;
  final int    port;
  const DiscoveryResult({required this.host, required this.port});
}

class DiscoveryService {
  static const int _listenPort = 47777;

  /// 監聽 UDP 廣播，在 [timeout] 內若收到伺服器訊號則回傳結果，否則回傳 null
  static Future<DiscoveryResult?> discover({
    Duration timeout = const Duration(seconds: 6),
    void Function(String status)? onStatus,
  }) async {
    onStatus?.call('搜尋伺服器中…');
    try {
      final socket = await RawDatagramSocket.bind(
        InternetAddress.anyIPv4,
        _listenPort,
        reuseAddress: true,
        reusePort:    false,
      );
      socket.broadcastEnabled = true;

      final completer = Completer<DiscoveryResult?>();

      final timer = Timer(timeout, () {
        if (!completer.isCompleted) {
          onStatus?.call('找不到伺服器');
          completer.complete(null);
        }
        socket.close();
      });

      socket.listen((RawSocketEvent event) {
        if (event != RawSocketEvent.read) return;
        final dg = socket.receive();
        if (dg == null) return;
        try {
          final text = String.fromCharCodes(dg.data);
          final data = jsonDecode(text) as Map<String, dynamic>;
          if (data['service'] == 'ai_glasses') {
            final host = dg.address.address;
            final port = (data['port'] as num).toInt();
            if (!completer.isCompleted) {
              timer.cancel();
              socket.close();
              onStatus?.call('找到伺服器：$host:$port');
              completer.complete(DiscoveryResult(host: host, port: port));
            }
          }
        } catch (_) {}
      });

      return completer.future;
    } catch (e) {
      onStatus?.call('UDP 監聽失敗：$e');
      return null;
    }
  }
}
