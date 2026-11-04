import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/backend.dart';
import 'package:myinterpreter_app/screens/portfolio.dart';
import 'support/fake_backend.dart';

class PortfolioFixture extends FakeBackend {
  bool failPrices = false;
  List<AppDocument> prices = const [
    AppDocument(
      id: 'a',
      data: {'c_name': 'Alpha', 'pa': 10, 'date': '2000-01-03T16:00:00Z'},
    ),
  ];
  @override
  Future<DocumentPage> listDocuments({
    required String collectionId,
    List<String> queries = const [],
  }) async {
    if (collectionId == 'portefeuille') {
      return const DocumentPage([
        AppDocument(
          id: 'one',
          data: {'c_name': 'Alpha', 'quantity': 2, 'total_cost': 15},
        ),
        AppDocument(
          id: 'two',
          data: {'c_name': 'Beta', 'quantity': 1, 'total_cost': 20},
        ),
      ]);
    }
    if (collectionId == 'latest_prices') {
      if (failPrices) throw const BackendFailure('Recorded prices unavailable');
      return DocumentPage(prices);
    }
    return const DocumentPage([]);
  }
}

class CurrentPortfolioFixture extends PortfolioFixture
    implements MarketDisplayBackend {
  @override
  bool get marketDisplayEnabled => true;
  late Map<String, dynamic> payload;
  @override
  Future<Object?> readMarketDisplay() async => payload;
}

class AdvancingReferenceFixture extends CurrentPortfolioFixture {
  int referenceReads = 0;
  @override
  Future<DocumentPage> listDocuments({
    required String collectionId,
    List<String> queries = const [],
  }) async {
    if (collectionId == 'latest_prices') {
      referenceReads++;
      return DocumentPage([
        AppDocument(
          id: 'reference',
          data: {
            'c_name': 'Alpha',
            'pa': referenceReads < 3 ? 530 : 524,
            'date': referenceReads < 3
                ? '2030-01-02T18:00:00Z'
                : '2030-01-03T18:00:00Z',
          },
        ),
      ]);
    }
    return super.listDocuments(collectionId: collectionId, queries: queries);
  }
}

void main() {
  late AppBackend previous;
  late PortfolioFixture fixture;
  setUp(() {
    previous = backend;
    fixture = PortfolioFixture()..signedIn = true;
    backend = fixture;
  });
  tearDown(() {
    backend = previous;
  });
  Future<void> render(WidgetTester tester, {DateTime Function()? clock}) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: PortfolioScreen(clock: clock)),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets(
    'expiry and next-morning resume fetch newly approved references',
    (tester) async {
      var now = DateTime.utc(2030, 1, 3, 18);
      final payload =
          jsonDecode(
                File(
                  '../tests/fixtures/shadow_market_preview_v3.json',
                ).readAsStringSync(),
              )
              as Map<String, dynamic>;
      final row = Map<String, dynamic>.from(
        (payload['rows'] as List).first as Map,
      );
      final expiry = now.add(const Duration(seconds: 1)).toIso8601String();
      row.addAll({
        'c_name': 'Alpha',
        'price_decimal': '526',
        'captured_at': now.toIso8601String(),
        'expires_at': expiry,
        'application_expires_at': expiry,
        'reported_day': '2030-01-03',
      });
      (row['application_fields'] as Map<String, dynamic>).addAll(
        <String, dynamic>{
          'c_name': 'Alpha',
          'pa': 526,
          'date': now.toIso8601String(),
        },
      );
      payload.addAll({
        'as_of': now.toIso8601String(),
        'captured_at': now.toIso8601String(),
        'rows': [row],
      });
      final current = AdvancingReferenceFixture()
        ..signedIn = true
        ..payload = payload;
      backend = current;
      await render(tester, clock: () => now);
      expect(find.textContaining('→ 526.00 MAD'), findsOneWidget);
      expect(current.referenceReads, 1);
      now = now.add(const Duration(seconds: 2));
      await tester.pump(const Duration(seconds: 2));
      await tester.pumpAndSettle();
      expect(current.referenceReads, 2);
      expect(find.textContaining('→ 530.00 MAD'), findsOneWidget);
      // The verified closing batch arrives after the live quote expired.
      now = now.add(const Duration(minutes: 15));
      await tester.pump(const Duration(minutes: 15));
      await tester.pumpAndSettle();
      expect(current.referenceReads, 3);
      expect(find.textContaining('→ 524.00 MAD'), findsOneWidget);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      now = DateTime.utc(2030, 1, 4, 7);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(current.referenceReads, 4);
      expect(find.textContaining('→ 524.00 MAD'), findsOneWidget);
      expect(current.trades, isEmpty);
    },
  );
  testWidgets(
    'fresh portfolio quote expires back to its dated reference without financial writes',
    (tester) async {
      var now = DateTime.utc(2030, 1, 3, 12);
      final value =
          jsonDecode(
                File(
                  '../tests/fixtures/shadow_market_preview_v3.json',
                ).readAsStringSync(),
              )
              as Map<String, dynamic>;
      final row = Map<String, dynamic>.from(
        (value['rows'] as List).first as Map,
      );
      final expiry = now.add(const Duration(seconds: 1)).toIso8601String();
      row.addAll({
        'c_name': 'Alpha',
        'price_decimal': '20',
        'captured_at': now.toIso8601String(),
        'expires_at': expiry,
        'application_expires_at': expiry,
        'reported_day': '2030-01-03',
      });
      (row['application_fields'] as Map<String, dynamic>).addAll(
        <String, dynamic>{
          'c_name': 'Alpha',
          'pa': 20,
          'date': now.toIso8601String(),
        },
      );
      value.addAll({
        'as_of': now.toIso8601String(),
        'captured_at': now.toIso8601String(),
        'rows': [row],
      });
      final current = CurrentPortfolioFixture()
        ..signedIn = true
        ..payload = value;
      backend = current;
      await render(tester, clock: () => now);
      expect(find.textContaining('Reported 2030-01-03'), findsOneWidget);
      expect(find.textContaining('→ 20.00 MAD'), findsOneWidget);
      now = now.add(const Duration(seconds: 2));
      await tester.pump(const Duration(seconds: 2));
      await tester.pumpAndSettle();
      expect(find.textContaining('Reported 2030-01-03'), findsNothing);
      expect(find.textContaining('Recorded 2000-01-03'), findsOneWidget);
      expect(find.textContaining('→ 10.00 MAD'), findsOneWidget);
      expect(current.trades, isEmpty);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'partial recorded prices show no current total or false portfolio loss',
    (tester) async {
      await render(tester);
      expect(find.text('Current'), findsNothing);
      expect(find.text('Reference estimate'), findsOneWidget);
      expect(
        find.textContaining('Totals need complete positions'),
        findsOneWidget,
      );
      expect(find.text('—'), findsWidgets);
      expect(find.text('35 MAD'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'complete old prices are explicitly reference estimates with recorded dates',
    (tester) async {
      fixture.prices = [
        ...fixture.prices,
        const AppDocument(
          id: 'b',
          data: {'c_name': 'Beta', 'pa': 25, 'date': '2000-01-03T16:00:00Z'},
        ),
      ];
      await render(tester);
      expect(find.text('45 MAD'), findsOneWidget);
      expect(
        find.textContaining('Estimates are not live quotes.'),
        findsOneWidget,
      );
      expect(find.text('Recorded 2000-01-03 (UTC)'), findsNWidgets(2));
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'unavailable price endpoint preserves positions and purchase cost',
    (tester) async {
      fixture.failPrices = true;
      await render(tester);
      expect(find.text('Alpha'), findsOneWidget);
      expect(find.text('Beta'), findsOneWidget);
      expect(find.text('35 MAD'), findsOneWidget);
      expect(
        find.textContaining('Totals need complete positions'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
    },
  );
}
