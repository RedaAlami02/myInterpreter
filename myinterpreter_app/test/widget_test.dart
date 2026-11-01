import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/backend.dart';
import 'package:myinterpreter_app/main.dart';
import 'package:myinterpreter_app/screens/login.dart';
import 'package:myinterpreter_app/screens/buy_sell_sheet.dart';
import 'support/fake_backend.dart';

void main() {
  late AppBackend previous;
  late FakeBackend fixture;
  setUp(() {
    previous = backend;
    fixture = FakeBackend();
    backend = fixture;
  });
  tearDown(() {
    backend = previous;
  });

  testWidgets(
    'fresh account sees login, then its empty portfolio, then logs out',
    (tester) async {
      await tester.pumpWidget(const MyApp());
      await tester.pumpAndSettle();
      expect(find.text('Sign in'), findsOneWidget);
      await tester.enterText(
        find.byType(TextField).at(0),
        'fixture@example.invalid',
      );
      await tester.enterText(find.byType(TextField).at(1), 'fixture-password');
      await tester.tap(find.byType(Checkbox));
      await tester.tap(find.widgetWithText(ElevatedButton, 'Log in'));
      await tester.pumpAndSettle();
      expect(fixture.lastRemember, isFalse);
      await tester.tap(
        find.byIcon(Icons.account_balance_wallet_outlined).first,
      );
      await tester.pumpAndSettle();
      expect(find.text('No holdings yet'), findsOneWidget);
      await tester.tap(find.byIcon(Icons.logout));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(TextButton, 'Déconnexion'));
      await tester.pumpAndSettle();
      expect(find.text('Sign in'), findsOneWidget);
      expect(fixture.signedIn, isFalse);
    },
  );

  testWidgets(
    'confirmation-required signup stays on login with useful notice',
    (tester) async {
      await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
      await tester.tap(find.text('Sign up'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).at(0), 'Fixture');
      await tester.enterText(
        find.byType(TextField).at(1),
        'fixture@example.invalid',
      );
      await tester.enterText(find.byType(TextField).at(2), 'fixture-password');
      await tester.tap(find.widgetWithText(ElevatedButton, 'Sign up'));
      await tester.pumpAndSettle();
      expect(
        find.textContaining('Check your email to confirm'),
        findsOneWidget,
      );
      expect(fixture.signedIn, isFalse);
      expect(find.widgetWithText(ElevatedButton, 'Log in'), findsOneWidget);
    },
  );

  testWidgets(
    'uncertain trade retry retains request identity and decimal inputs',
    (tester) async {
      fixture.failFirstTrade = true;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => ElevatedButton(
                onPressed: () => showBuySellSheet(context, 'Fixture', 100.15),
                child: const Text('Open trade'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open trade'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).at(0), '2.5');
      await tester.tap(find.byType(ElevatedButton).last);
      await tester.pumpAndSettle();
      expect(find.textContaining('Uncertain response'), findsOneWidget);
      await tester.enterText(find.byType(TextField).at(1), '101.15');
      await tester.tap(find.byType(ElevatedButton).last);
      await tester.pumpAndSettle();
      expect(fixture.trades.length, 1);
      expect(find.textContaining('Check your holdings'), findsOneWidget);
      await tester.enterText(find.byType(TextField).at(1), '100.15');
      await tester.tap(find.byType(ElevatedButton).last);
      await tester.pumpAndSettle();
      expect(fixture.trades.length, 2);
      expect(fixture.trades[0], fixture.trades[1]);
      expect(fixture.trades[1]['quantity'], '2.5');
      expect(fixture.trades[1]['price'], '100.15');
    },
  );
}
