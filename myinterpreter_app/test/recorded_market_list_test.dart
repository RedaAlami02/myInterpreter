import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/backend_contract.dart';
import 'package:myinterpreter_app/recorded_market_list.dart';
import 'support/fake_backend.dart';

class RecordedFixture extends FakeBackend {
  int reads = 0;
  @override
  Future<DocumentPage> listDocuments({
    required String collectionId,
    List<String> queries = const [],
  }) async {
    reads++;
    expect(collectionId, 'latest_prices');
    return const DocumentPage([
      AppDocument(
        id: 'a',
        data: {
          'c_name': 'Dated company',
          'pa': '216.00',
          'date': '2026-01-01T12:00:00Z',
        },
      ),
      AppDocument(
        id: 'b',
        data: {
          'c_name': 'Future company',
          'pa': '100',
          'date': '2099-01-01T12:00:00Z',
        },
      ),
    ]);
  }
}

void main() {
  testWidgets('old dated references remain explicit and search is local', (
    tester,
  ) async {
    final source = RecordedFixture();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: RecordedMarketList(source: source, onRefresh: () async {}),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('216.00 MAD'), findsOneWidget);
    expect(find.text('Prix enregistré · 2026-01-01 (UTC)'), findsOneWidget);
    expect(find.text('Future company'), findsNothing);
    await tester.enterText(find.byType(TextField), 'missing');
    await tester.pumpAndSettle();
    expect(find.text('216.00 MAD'), findsNothing);
    expect(source.reads, 1);
  });
}
