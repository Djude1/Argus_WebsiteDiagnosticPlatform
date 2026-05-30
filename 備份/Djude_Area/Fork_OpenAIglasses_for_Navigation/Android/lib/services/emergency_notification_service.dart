// lib/services/emergency_notification_service.dart
// 背景摔倒偵測通知服務：App 待機時偵測到撞擊，顯示全螢幕緊急通知
// 利用 flutter_local_notifications fullScreenIntent 在鎖定畫面也能顯示

import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class EmergencyNotificationService {
  // 單例
  static final EmergencyNotificationService _instance =
      EmergencyNotificationService._internal();
  factory EmergencyNotificationService() => _instance;
  EmergencyNotificationService._internal();

  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  static const int    _notificationId = 9001;
  static const String _channelId      = 'emergency_fall';

  // ── 初始化（在 main() 中呼叫一次）──────────────────────────────────────────
  Future<void> initialize() async {
    const androidInit = AndroidInitializationSettings('@mipmap/ic_launcher');
    const initSettings = InitializationSettings(android: androidInit);
    await _plugin.initialize(initSettings);

    // 建立高重要性通知頻道（Android 8.0+ 必須）
    const channel = AndroidNotificationChannel(
      _channelId,
      '緊急摔倒警示',
      description: '偵測到摔倒或碰撞時發出警示通知',
      importance: Importance.max,
      enableVibration: true,
      playSound:       true,
    );
    await _plugin
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(channel);
  }

  // ── 顯示全螢幕緊急通知（鎖定畫面可見）──────────────────────────────────────
  Future<void> showFallAlert(double magnitude) async {
    final g = (magnitude / 9.8).toStringAsFixed(1);
    const androidDetails = AndroidNotificationDetails(
      _channelId,
      '緊急摔倒警示',
      channelDescription: '偵測到摔倒或碰撞時發出警示通知',
      importance:      Importance.max,
      priority:        Priority.max,
      fullScreenIntent: true,             // 全螢幕顯示（鎖定畫面也能看到）
      category:        AndroidNotificationCategory.alarm,
      visibility:      NotificationVisibility.public,   // 鎖定畫面顯示全文
      autoCancel:      true,
    );
    const details = NotificationDetails(android: androidDetails);
    await _plugin.show(
      _notificationId,
      '⚠️ 偵測到摔倒！',
      '加速度 ${g}G，請點擊確認狀態或撥打緊急電話',
      details,
    );
  }

  // ── 取消通知（App 回到前台後清除）──────────────────────────────────────────
  Future<void> cancelFallAlert() async {
    await _plugin.cancel(_notificationId);
  }
}
