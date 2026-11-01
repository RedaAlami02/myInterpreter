import 'dart:convert';
import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/backend.dart';
import 'package:myinterpreter_app/market_preview.dart';
import 'package:myinterpreter_app/screens/screener.dart';
import 'package:myinterpreter_app/screens/stock_detail.dart';
import 'package:myinterpreter_app/shadow_market_feed.dart';
import 'support/fake_backend.dart';

Map<String, dynamic> payload() =>
    jsonDecode(
          File(
            '../tests/fixtures/market_screen_preview.json',
          ).readAsStringSync(),
        )
        as Map<String, dynamic>;

class PreviewBackend extends FakeBackend implements MarketDisplayBackend {
  @override
  bool marketDisplayEnabled = true;
  int previewReads = 0;
  final historyReads = <String>[];
  bool fail = false;
  Completer<DocumentPage>? pendingHistory;
  DocumentPage historyResponse = const DocumentPage([]);
  Map<String, dynamic> value = payload();
  @override
  Future<Object?> readMarketDisplay() async {
    previewReads++;
    if (fail) throw StateError('private-fixture-diagnostic');
    return value;
  }

  @override
  Future<DocumentPage> listDocuments({
    required String collectionId,
    List<String> queries = const [],
  }) async {
    historyReads.add(collectionId);
    if (pendingHistory != null) return await pendingHistory!.future;
    return historyResponse;
  }
}

void main() {
  late AppBackend previous;
  late PreviewBackend fixture;
  final instant = DateTime.parse('2026-10-28T12:05:00Z');
  setUp(() {
    previous = backend;
    fixture = PreviewBackend();
    backend = fixture;
  });
  tearDown(() {
    backend = previous;
  });

  testWidgets(
    'market screen opts in without history fallback or portfolio action',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: ScreenerScreen(marketClock: () => instant)),
        ),
      );
      await tester.pumpAndSettle();
      expect(fixture.previewReads, 1);
      expect(fixture.historyReads, isEmpty);
      expect(find.text('21.25 MAD'), findsOneWidget);
      expect(find.textContaining('Date de cotation inconnue.'), findsOneWidget);
      expect(find.textContaining('heure inconnue'), findsNWidgets(2));
      expect(find.text('MASI'), findsOneWidget);
      expect(find.text('1234.56 points'), findsOneWidget);
      expect(find.byIcon(Icons.add_shopping_cart), findsNothing);
      await tester.enterText(find.byType(TextField), 'B');
      await tester.pump();
      expect(find.text('Company B'), findsOneWidget);
      expect(find.text('Company A'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('default path does not request the preview', (tester) async {
    fixture.marketDisplayEnabled = false;
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: ScreenerScreen())),
    );
    await tester.pumpAndSettle();
    expect(fixture.previewReads, 0);
    expect(fixture.historyReads, ['data']);
  });

  testWidgets(
    'disabled, missing and failed feeds remain explicit without stale fallback',
    (tester) async {
      fixture.value = {...payload(), 'status': 'DISABLED', 'rows': <Object>[]};
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: ScreenerScreen(marketClock: () => instant)),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        find.textContaining('Les cours récents sont indisponibles.'),
        findsOneWidget,
      );
      expect(fixture.historyReads, isEmpty);
      fixture.fail = true;
      await tester.tap(find.text('Actualiser'));
      await tester.pumpAndSettle();
      expect(find.textContaining('private-fixture-diagnostic'), findsNothing);
      expect(find.text('21.25 MAD'), findsNothing);
      expect(fixture.historyReads, isEmpty);
    },
  );

  testWidgets('price and ratios expire at their own deadline and on resume', (
    tester,
  ) async {
    var now = instant;
    final snapshot = ShadowMarketSnapshot.fromJson(payload());
    await tester.pumpWidget(
      MaterialApp(
        home: ExpiringMarketRows(
          quotes: snapshot.rows,
          clock: () => now,
          builder: (context, rows) => Column(
            children: [
              for (final row in rows)
                Text(
                  '${row['c_name']}:${row['pa'] ?? '—'}/${row['per'] ?? '—'}',
                ),
            ],
          ),
        ),
      ),
    );
    expect(find.text('Company B:21.25/12.5'), findsOneWidget);
    now = instant.add(const Duration(minutes: 5));
    await tester.pump(const Duration(minutes: 5));
    expect(find.text('Company B:—/—'), findsOneWidget);
    expect(find.text('Company A:10.5/12.5'), findsOneWidget);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    now = instant.add(const Duration(days: 1));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(find.text('Company A:—/—'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(days: 1));
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'detail keeps reference separate from historical chart and trade forms',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: ScreenerScreen(marketClock: () => instant)),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Company B'));
      await tester.pumpAndSettle();
      expect(find.text('Historique enregistré'), findsOneWidget);
      expect(find.textContaining('Prix de référence'), findsOneWidget);
      expect(find.byType(FloatingActionButton), findsNothing);
      expect(fixture.historyReads, ['data']);
      expect(fixture.trades, isEmpty);
    },
  );

  testWidgets('current detail remains visible while history loads or fails', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: ScreenerScreen(marketClock: () => instant)),
      ),
    );
    await tester.pumpAndSettle();
    fixture.pendingHistory = Completer<DocumentPage>();
    await tester.tap(find.text('Company B'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(
      find.descendant(
        of: find.byType(StockDetailScreen),
        matching: find.text('21.25 MAD'),
      ),
      findsOneWidget,
    );
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    fixture.pendingHistory!.completeError(
      StateError('private-history-fixture'),
    );
    await tester.pumpAndSettle();
    expect(find.text('21.25 MAD'), findsOneWidget);
    expect(
      find.text('Historique indisponible. Réessayez plus tard.'),
      findsOneWidget,
    );
    expect(find.textContaining('private-history-fixture'), findsNothing);
    expect(find.byType(FloatingActionButton), findsNothing);
  });

  testWidgets(
    'index current and historical values use points without trading controls',
    (tester) async {
      fixture.historyResponse = const DocumentPage([
        AppDocument(
          id: 'index-one',
          data: {
            'c_name': 'MASI',
            'pa': 1230.0,
            'date': '2026-10-28T12:00:00Z',
          },
        ),
        AppDocument(
          id: 'index-two',
          data: {
            'c_name': 'MASI',
            'pa': 1220.0,
            'date': '2026-10-27T12:00:00Z',
          },
        ),
      ]);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: ScreenerScreen(marketClock: () => instant)),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('MASI'));
      await tester.tap(find.text('MASI'));
      await tester.pumpAndSettle();
      expect(find.text('1234.56 points'), findsOneWidget);
      expect(find.text('1230.0 points'), findsOneWidget);
      expect(find.textContaining('MAD'), findsNothing);
      expect(find.byType(FloatingActionButton), findsNothing);
    },
  );

  testWidgets(
    'phone layout renders with current price context and no overflow',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final key = GlobalKey();
      await tester.pumpWidget(
        RepaintBoundary(
          key: key,
          child: MaterialApp(
            theme: ThemeData.dark(),
            home: Scaffold(
              appBar: AppBar(title: const Text('Marché')),
              body: ScreenerScreen(marketClock: () => instant),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      final screenshot = Platform.environment['MARKET_PREVIEW_SCREENSHOT'];
      if (screenshot != null) {
        final file = File(screenshot);
        final parent = file.parent.resolveSymbolicLinksSync();
        final private = Directory('../private').resolveSymbolicLinksSync();
        if (!parent.startsWith('$private${Platform.pathSeparator}')) {
          throw StateError('Screenshot must stay private');
        }
        await tester.runAsync(() async {
          final boundary =
              key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
          final image = await boundary.toImage();
          final data = await image.toByteData(format: ui.ImageByteFormat.png);
          await file.writeAsBytes(data!.buffer.asUint8List());
          image.dispose();
        });
      }
    },
  );
}
