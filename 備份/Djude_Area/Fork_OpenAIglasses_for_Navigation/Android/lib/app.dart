// lib/app.dart
// MaterialApp 根節點與路由設定

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/theme.dart';
import 'providers/app_provider.dart';
import 'screens/splash_screen.dart';
import 'screens/mode_select_screen.dart';
import 'screens/blind_screen.dart';
import 'screens/home_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/read_screen.dart';
import 'screens/nav_destination_screen.dart';
import 'screens/yoloe_ar_test_screen.dart';
import 'screens/customer_service_screen.dart';
import 'widgets/asr_status_overlay.dart';

class AiGlassesApp extends StatelessWidget {
  const AiGlassesApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AppProvider()),
      ],
      child: MaterialApp(
        title: 'AI智慧眼鏡',
        navigatorKey: AppProvider.navigatorKey,
        debugShowCheckedModeBanner: false,
        theme: AppTheme.dark,
        // 全域 ASR 狀態 overlay：所有頁面右上角顯示聆聽/處理中 + partial 辨識文字
        builder: (context, child) =>
            AsrStatusOverlay(child: child ?? const SizedBox.shrink()),
        initialRoute: '/splash',
        routes: {
          '/splash':      (_) => const SplashScreen(),
          '/mode_select': (_) => const ModeSelectScreen(),
          '/blind':       (_) => const BlindScreen(),
          '/home':        (_) => const HomeScreen(),
          '/settings':    (_) => const SettingsScreen(),
          '/read':        (_) => const ReadScreen(),
          '/nav_dest':    (_) => const NavDestinationScreen(),
          '/yoloe_ar_test': (_) => const YoloeArTestScreen(),
          '/support':       (_) => const CustomerServiceScreen(),
        },
      ),
    );
  }
}
