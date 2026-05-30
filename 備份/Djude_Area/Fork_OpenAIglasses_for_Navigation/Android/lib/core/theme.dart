// lib/core/theme.dart
// 視障友善主題：高對比、大字體、清晰觸控目標

import 'package:flutter/material.dart';

class AppTheme {
  // ── 顏色 ─────────────────────────────────────────────────────────────────
  static const Color primary    = Color(0xFF1565C0); // 深藍
  static const Color onPrimary  = Colors.white;
  static const Color background = Color(0xFF121212); // 深黑
  static const Color surface    = Color(0xFF1E1E1E);
  static const Color onSurface  = Colors.white;
  static const Color error      = Color(0xFFCF6679);

  // 各功能按鈕顏色（高對比）
  static const Color colorBlindpath    = Color(0xFF1976D2); // 藍
  static const Color colorCrossing     = Color(0xFF388E3C); // 綠
  static const Color colorTrafficLight = Color(0xFFF57C00); // 橘
  static const Color colorItemSearch   = Color(0xFF7B1FA2); // 紫
  static const Color colorStop         = Color(0xFFD32F2F); // 紅

  // ── 主題建構 ─────────────────────────────────────────────────────────────
  static ThemeData get dark => ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: const ColorScheme.dark(
      primary:   primary,
      onPrimary: onPrimary,
      surface:   surface,
      onSurface: onSurface,
      error:     error,
    ),
    scaffoldBackgroundColor: background,
    // 大字體（預設放大 1.2x，讓視障者更容易閱讀）
    textTheme: const TextTheme(
      displayLarge:  TextStyle(fontSize: 32, fontWeight: FontWeight.bold,   color: Colors.white),
      displayMedium: TextStyle(fontSize: 28, fontWeight: FontWeight.bold,   color: Colors.white),
      headlineLarge: TextStyle(fontSize: 24, fontWeight: FontWeight.bold,   color: Colors.white),
      headlineMedium:TextStyle(fontSize: 20, fontWeight: FontWeight.w600,   color: Colors.white),
      bodyLarge:     TextStyle(fontSize: 18, fontWeight: FontWeight.normal, color: Colors.white),
      bodyMedium:    TextStyle(fontSize: 16, fontWeight: FontWeight.normal, color: Colors.white70),
      labelLarge:    TextStyle(fontSize: 18, fontWeight: FontWeight.bold,   color: Colors.white),
    ),
    // 按鈕大字體
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        minimumSize: const Size(double.infinity, 64),
        textStyle: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
    // 輸入框
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: surface,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
      labelStyle: const TextStyle(fontSize: 16, color: Colors.white70),
      hintStyle:  const TextStyle(fontSize: 16, color: Colors.white38),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: Color(0xFF0D0D0D),
      foregroundColor: Colors.white,
      elevation: 0,
      titleTextStyle: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.white),
    ),
  );
}
