import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/theme.dart';
import 'features/settings/server_settings.dart';
import 'pages/main_page.dart';

/// Application root widget with Riverpod and navigation.
class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ProviderScope(
      child: MaterialApp(
        title: 'Visual Impairment Assistant',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.darkTheme,
        home: const MainPage(),
        routes: {
          '/settings': (context) => const ServerSettingsPage(),
        },
      ),
    );
  }
}
