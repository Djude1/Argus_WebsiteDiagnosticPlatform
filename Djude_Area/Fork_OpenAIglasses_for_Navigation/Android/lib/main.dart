// lib/main.dart
// 應用程式進入點

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';

import 'app.dart';
import 'services/emergency_notification_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // 固定直向螢幕（視障者使用習慣）
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);

  // 初始化前台服務設定（flutter_foreground_task 8.x API）
  _initForegroundTask();

  // 初始化背景摔倒偵測通知服務（初始化失敗不阻擋 APP 啟動）
  try {
    await EmergencyNotificationService().initialize();
  } catch (e) {
    // 通知服務初始化失敗（部分裝置權限未授予），繼續啟動
    debugPrint('EmergencyNotificationService init failed: $e');
  }

  runApp(const AiGlassesApp());
}

void _initForegroundTask() {
  FlutterForegroundTask.init(
    androidNotificationOptions: AndroidNotificationOptions(
      channelId:          'ai_glasses_foreground',
      channelName:        'AI智慧眼鏡背景服務',
      channelDescription: '持續監聽喚醒詞，確保隨時可以回應語音指令',
      channelImportance:  NotificationChannelImportance.LOW,
      priority:           NotificationPriority.LOW,
      // 8.x 已移除 iconData 參數，改用 App 預設圖示
    ),
    iosNotificationOptions: const IOSNotificationOptions(
      showNotification: true,
      playSound: false,
    ),
    // repeat(5000) 不是 const，不能加 const 關鍵字
    foregroundTaskOptions: ForegroundTaskOptions(
      eventAction:    ForegroundTaskEventAction.repeat(5000),
      autoRunOnBoot:  true,
      allowWakeLock:  true,
    ),
  );
}
