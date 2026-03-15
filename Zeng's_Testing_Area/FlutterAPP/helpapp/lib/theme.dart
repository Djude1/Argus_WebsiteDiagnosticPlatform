import 'package:flutter/material.dart';

class AppTheme {
  static ThemeData get highContrastTheme {
    return ThemeData(
      scaffoldBackgroundColor: Colors.black,
      colorScheme: const ColorScheme.dark(
        primary: Colors.yellow,
        secondary: Colors.yellowAccent,
        surface: Colors.black,
        error: Colors.red,
        onPrimary: Colors.black,
        onSecondary: Colors.black,
        onSurface: Colors.yellow,
        onError: Colors.black,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.black,
        foregroundColor: Colors.yellow,
        iconTheme: IconThemeData(color: Colors.yellow),
      ),
      textTheme: const TextTheme(
        bodyLarge: TextStyle(color: Colors.yellow),
        bodyMedium: TextStyle(color: Colors.yellow),
        bodySmall: TextStyle(color: Colors.yellow),
        displayLarge: TextStyle(color: Colors.yellow),
        displayMedium: TextStyle(color: Colors.yellow),
        displaySmall: TextStyle(color: Colors.yellow),
        headlineLarge: TextStyle(color: Colors.yellow),
        headlineMedium: TextStyle(color: Colors.yellow),
        headlineSmall: TextStyle(color: Colors.yellow),
        titleLarge: TextStyle(color: Colors.yellow),
        titleMedium: TextStyle(color: Colors.yellow),
        titleSmall: TextStyle(color: Colors.yellow),
        labelLarge: TextStyle(color: Colors.yellow),
        labelMedium: TextStyle(color: Colors.yellow),
        labelSmall: TextStyle(color: Colors.yellow),
      ),
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: Colors.yellow,
        foregroundColor: Colors.black,
      ),
      iconTheme: const IconThemeData(
        color: Colors.yellow,
      ),
    );
  }
}
