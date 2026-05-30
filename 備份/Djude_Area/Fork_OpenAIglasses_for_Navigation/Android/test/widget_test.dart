// 基本 smoke test（僅確認 App widget 可以建立）
import 'package:flutter_test/flutter_test.dart';
import 'package:android_ai_glasses/app.dart';

void main() {
  testWidgets('App smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const AiGlassesApp());
  });
}
