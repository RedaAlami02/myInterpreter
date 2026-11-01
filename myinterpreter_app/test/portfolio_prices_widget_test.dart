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
  Future<void> render(WidgetTester tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: PortfolioScreen())),
    );
    await tester.pumpAndSettle();
  }

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
