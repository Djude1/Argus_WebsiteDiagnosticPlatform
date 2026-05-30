import 'package:flutter_test/flutter_test.dart';

import 'package:visual_impairment_assistant/app.dart';

void main() {
  testWidgets('App smoke test', (WidgetTester tester) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const MyApp());

    // Verify that the app loads with tabs
    expect(find.text('Camera'), findsOneWidget);
    expect(find.text('Voice'), findsOneWidget);
  });
}
