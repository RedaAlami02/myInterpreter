import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/backend.dart';
import 'package:myinterpreter_app/main.dart';
import 'package:myinterpreter_app/screens/buy_sell_sheet.dart';
import 'package:myinterpreter_app/screens/screener.dart';
import 'package:myinterpreter_app/screens/stock_detail.dart';
import 'support/fake_backend.dart';

class LossBackend extends FakeBackend {
  @override
  Future<DocumentPage> listDocuments({
    required String collectionId,
    List<String> queries = const [],
  }) async => DocumentPage([
    AppDocument(
      id: 'loss',
      data: {'c_name': 'CARTIER SAADA', 'pa': 19.15, 'per': -3.9},
    ),
  ]);
}

class IndexBackend extends FakeBackend {
  @override
  Future<DocumentPage> listDocuments({
    required String collectionId,
    List<String> queries = const [],
  }) async => DocumentPage([
    AppDocument(
      id: 'index',
      data: {'c_name': 'MASI', 'pa': 16934.5897, 'per': 12.0},
    ),
  ]);
}

void main() {
  late AppBackend previous;
  setUp(() {
    previous = backend;
    backend = FakeBackend();
  });
  tearDown(() {
    backend = previous;
  });

  testWidgets('legacy index has points and no purchase or ratios', (
    tester,
  ) async {
    backend = IndexBackend();
    await tester.pumpWidget(
      MaterialApp(
        theme: buildTheme(),
        home: const Scaffold(body: ScreenerScreen()),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('16934.59 points'), findsOneWidget);
    expect(find.byTooltip('Ajouter un achat'), findsNothing);
    expect(find.text('PER'), findsNothing);
    expect(find.text('PER 12.0'), findsNothing);
  });

  testWidgets('a loss-making PER is not shown as a headline figure', (
    tester,
  ) async {
    backend = LossBackend();
    await tester.pumpWidget(
      MaterialApp(
        theme: buildTheme(),
        home: const Scaffold(body: ScreenerScreen()),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('19.15 MAD'), findsOneWidget);
    expect(find.text('PER -3.9'), findsNothing);
  });

  testWidgets('trade scrolls above keyboard and accepts decimal comma', (
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
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () =>
                  showBuySellSheet(context, 'Société de démonstration', 10),
              child: const Text('Ouvrir'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Ouvrir'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.enterText(find.byType(TextField).first, '2,5');
    await tester.enterText(find.byType(TextField).last, '10,15');
    final confirm = find.text('Confirmer l’achat');
    await tester.ensureVisible(confirm);
    await tester.pumpAndSettle();
    await tester.tap(confirm);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect((backend as FakeBackend).trades.single['quantity'], '2.5');
    expect((backend as FakeBackend).trades.single['price'], '10.15');
  });

  testWidgets('empty history and ranges fit enlarged phone text', (
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
          data: MediaQuery.of(
            context,
          ).copyWith(textScaler: const TextScaler.linear(1.5)),
          child: child!,
        ),
        home: const StockDetailScreen(name: 'T2S Group Holding'),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.text('Aucun historique disponible pour cette période.'),
      findsOneWidget,
    );
    expect(find.text('Semaine'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
