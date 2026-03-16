// lib/app.dart
// MaterialApp 根節點與路由設定

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/theme.dart';
import 'providers/auth_provider.dart';
import 'providers/app_provider.dart';
import 'screens/splash_screen.dart';
import 'screens/home_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/contacts_screen.dart';
import 'screens/ar_screen.dart';
import 'screens/admin_login_screen.dart';
import 'screens/admin/admin_screen.dart';
import 'screens/admin/user_manage_screen.dart';

class AiGlassesApp extends StatelessWidget {
  const AiGlassesApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthProvider()),
        ChangeNotifierProvider(create: (_) => AppProvider()),
      ],
      child: MaterialApp(
        title: 'AI智慧眼鏡',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.dark,
        initialRoute: '/splash',
        routes: {
          '/splash':       (_) => const SplashScreen(),
          '/home':         (_) => const HomeScreen(),
          '/settings':     (_) => const SettingsScreen(),
          '/contacts':     (_) => const ContactsScreen(),
          '/admin_login':  (_) => const AdminLoginScreen(),
          '/admin':        (_) => const AdminScreen(),
          '/admin/users':  (_) => const UserManageScreen(),
        },
      ),
    );
  }
}
