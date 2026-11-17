import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/main.dart';
import 'package:myinterpreter_app/screens/login.dart';

void main() {
  testWidgets('French login wraps with enlarged text and keyboard', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        theme: buildTheme(),
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(
            textScaler: const TextScaler.linear(1.5),
            viewInsets: const EdgeInsets.only(bottom: 240),
          ),
          child: child!,
        ),
        home: const LoginScreen(),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.ensureVisible(find.text('Créer un compte'));
    await tester.tap(find.text('Créer un compte'));
    await tester.pumpAndSettle();
    expect(find.text('Nom (facultatif)'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
