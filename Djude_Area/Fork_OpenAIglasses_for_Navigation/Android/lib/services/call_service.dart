// lib/services/call_service.dart
// 直接撥打電話（不開啟撥號盤）
// 使用 ACTION_CALL intent + CALL_PHONE 權限

import 'package:android_intent_plus/android_intent.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:url_launcher/url_launcher.dart';

class CallService {
  /// 直接撥打電話
  /// 1. 檢查並請求 CALL_PHONE 權限
  /// 2. 已取得 → 用 ACTION_CALL 直接撥出（不需使用者再按）
  /// 3. 被拒絕 → 退回 tel: scheme（開啟撥號盤）
  static Future<void> call(String phone) async {
    if (phone.isEmpty) return;

    final status = await Permission.phone.request();

    if (status.isGranted) {
      try {
        // 直接撥打，不開啟撥號盤
        final intent = AndroidIntent(
          action: 'android.intent.action.CALL',
          data:   'tel:$phone',
        );
        await intent.launch();
      } catch (_) {
        // intent 失敗時退回撥號盤
        await launchUrl(Uri(scheme: 'tel', path: phone));
      }
    } else {
      // 退回開啟撥號盤
      await launchUrl(Uri(scheme: 'tel', path: phone));
    }
  }
}
