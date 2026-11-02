import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/backend.dart';
import 'package:myinterpreter_app/screens/home.dart';
import 'package:myinterpreter_app/trade_submission.dart';
import 'support/fake_backend.dart';

class RefreshFixture extends FakeBackend {
  int quantity = 1;
  final reads = <String, int>{};
  @override
  Future<DocumentPage> listDocuments({
    required String collectionId,
    List<String> queries = const [],
  }) async {
    reads.update(collectionId, (n) => n + 1, ifAbsent: () => 1);
    if (collectionId == 'portefeuille') {
      return DocumentPage([
        AppDocument(
          id: 'holding',
          data: {
            'c_name': 'Alpha',
            'quantity': quantity,
            'total_cost': quantity * 10,
          },
        ),
      ]);
    }
    return const DocumentPage([]);
  }

  @override
  Future<void> recordTrade({
    required String requestId,
    required bool isBuy,
    required String company,
    required String quantity,
    required String price,
  }) async {
    await super.recordTrade(
      requestId: requestId,
      isBuy: isBuy,
      company: company,
      quantity: quantity,
      price: price,
    );
    this.quantity = 2;
  }
}

void main() {
  late AppBackend previous;
  late RefreshFixture fixture;
  setUp(() {
    previous = backend;
    fixture = RefreshFixture()..signedIn = true;
    backend = fixture;
  });
  tearDown(() => backend = previous);
  TradeSubmission submission() => TradeSubmission(
    isBuy: true,
    company: 'Alpha',
    quantity: '1',
    price: '10',
  );

  testWidgets('confirmed trade refreshes holdings and hidden statistics once', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.account_balance_wallet_outlined).first);
    await tester.pumpAndSettle();
    expect(find.text('1 shares'), findsOneWidget);
    final portfolios = fixture.reads['portefeuille']!;
    final purchases = fixture.reads['achats']!;
    final trade = submission();
    await trade.submit(fixture);
    await tester.pumpAndSettle();
    expect(find.text('2 shares'), findsOneWidget);
    expect(fixture.reads['portefeuille'], portfolios + 1);
    expect(fixture.reads['achats'], purchases + 1);
    await trade.submit(fixture);
    await tester.pumpAndSettle();
    expect(fixture.reads['portefeuille'], portfolios + 1);
    expect(fixture.reads['achats'], purchases + 1);
  });

  testWidgets('uncertain response does not pretend success; retry refreshes', (
    tester,
  ) async {
    fixture.failFirstTrade = true;
    await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
    await tester.pumpAndSettle();
    final initial = fixture.reads['portefeuille'];
    final trade = submission();
    await expectLater(trade.submit(fixture), throwsA(isA<BackendFailure>()));
    await tester.pumpAndSettle();
    expect(fixture.reads['portefeuille'], initial);
    await trade.submit(fixture);
    await tester.pumpAndSettle();
    expect(fixture.reads['portefeuille'], initial! + 1);
    expect(fixture.trades[0]['id'], fixture.trades[1]['id']);
  });

  testWidgets('disposed account screens stop receiving invalidations', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
    await tester.pumpAndSettle();
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    await tester.pumpAndSettle();
    final initial = Map<String, int>.from(fixture.reads);
    await submission().submit(fixture);
    await tester.pumpAndSettle();
    expect(fixture.reads, initial);
    expect(tester.takeException(), isNull);
  });
}
