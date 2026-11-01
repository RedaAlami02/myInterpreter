import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/backend_contract.dart';
import 'package:myinterpreter_app/shadow_market_feed.dart';

Map<String, dynamic> fixture([int version = 1]) =>
    jsonDecode(
          File(
            version == 2
                ? '../tests/fixtures/shadow_market_preview_v2.json'
                : '../tests/fixtures/shadow_market_preview.json',
          ).readAsStringSync(),
        )
        as Map<String, dynamic>;

void main() {
  Map<String, dynamic> applicationFixture() =>
      jsonDecode(
            File(
              Platform.environment['APP_ROWS_FIXTURE'] ??
                  '../tests/fixtures/shadow_market_preview_v3.json',
            ).readAsStringSync(),
          )
          as Map<String, dynamic>;

  test(
    'v3 full application fields preserve reference semantics and expire',
    () {
      final payload = applicationFixture();
      final now = DateTime.parse(payload['as_of'] as String);
      final snapshot = ShadowMarketSnapshot.fromJson(payload);
      expect(
        snapshot.rows
            .map((row) => row.applicationRowAt(now))
            .whereType<Map>()
            .length,
        payload['rows'].length,
      );
      final quote = snapshot.rows.singleWhere(
        (row) => row.referencePrice != null,
      );
      expect(quote.priceAt(now), isNull);
      final view = quote.applicationRowAt(now)!;
      expect(view['price_basis'], 'INSTRUMENT_REFERENCE');
      expect(view['portfolio_valuation_eligible'], false);
      expect(view['source_event_at'], isNull);
      expect(view['reported_day'], isNull);
      expect(view['fields']['pa'], 21.25);
      expect(
        quote.applicationRowAt(now.subtract(const Duration(days: 1))),
        isNull,
      );
      expect(quote.applicationRowAt(now.add(const Duration(days: 1))), isNull);
      expect(() => view['fields']['pa'] = 999, throwsUnsupportedError);
    },
  );
  test('v3 rejects mismatched full rows and strips private fields', () {
    for (final change in {
      'pa': 999,
      'c_name': 'Other',
      'date': '2026-01-01T12:00:00Z',
      'per': true,
      'per_rating': 'trusted',
      'qty_traded': 1.5,
    }.entries) {
      final payload = applicationFixture();
      payload['rows'][0]['application_fields'][change.key] = change.value;
      expect(
        () => ShadowMarketSnapshot.fromJson(payload),
        throwsA(isA<BackendFailure>()),
      );
    }
    final payload = applicationFixture();
    payload['rows'][0]['application_fields']['internal_binding'] =
        'private-fixture';
    final view = ShadowMarketSnapshot.fromJson(
      payload,
    ).rows.first.applicationRowAt(DateTime.parse(payload['as_of']));
    expect(view!['fields'].containsKey('internal_binding'), false);
    for (final change in {
      'reported_day': '2026-02-30',
      'source_event_at': {'internal_binding': 'private-fixture'},
    }.entries) {
      final bad = applicationFixture();
      bad['rows'][0][change.key] = change.value;
      expect(
        () => ShadowMarketSnapshot.fromJson(bad),
        throwsA(isA<BackendFailure>()),
      );
    }
  });
  test(
    'conflicting instrument references cannot be hidden by saved prices',
    () {
      final data = fixture(2);
      data['rows'][1]['reference_price'] = null;
      data['rows'][1]['reference_conflict'] = true;
      final quote = ShadowMarketSnapshot.fromJson(data).rows[1];
      const saved = AppDocument(
        id: 'old',
        data: {
          'c_name': 'Company B',
          'pa': '19.75',
          'date': '2026-10-27T12:00:00Z',
        },
      );
      final now = DateTime.parse('2026-10-28T12:05:00Z');
      expect(quote.displayPriceAt(now, lastKnown: saved), isNull);
      expect(
        quote.displayPriceBasisAt(now, lastKnown: saved),
        'CONFLICTING_INSTRUMENT_PRICES',
      );
    },
  );
  test('SQL display fixture reaches the mobile display reader', () {
    final path =
        Platform.environment['MARKET_DISPLAY_FIXTURE'] ??
        '../tests/fixtures/shadow_market_preview_v2.json';
    final payload =
        jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
    final snapshot = ShadowMarketSnapshot.fromJson(payload);
    final now = DateTime.parse(payload['as_of'] as String);
    final refs = snapshot.rows
        .where((row) => row.referencePrice != null)
        .toList();
    expect(refs.length, 1);
    expect(refs.single.priceAt(now), isNull);
    expect(refs.single.displayPriceAt(now), '21.25');
    expect(refs.single.displayPriceBasisAt(now), 'INSTRUMENT_REFERENCE');
  });
  test(
    'v2 reference displays separately and retains missing quote semantics',
    () {
      final quote = ShadowMarketSnapshot.fromJson(fixture(2)).rows[1];
      final now = DateTime.parse('2026-10-28T12:05:00Z');
      expect(quote.priceAt(now), isNull);
      expect(quote.displayPriceAt(now), '21.25');
      expect(quote.displayPriceBasisAt(now), 'INSTRUMENT_REFERENCE');
      expect(
        quote.displayPriceAt(DateTime.parse('2026-10-28T12:10:00Z')),
        isNull,
      );
      expect(
        quote.displayPriceAt(DateTime.parse('2026-10-28T11:59:00Z')),
        isNull,
      );
    },
  );
  test(
    'saved-price fallback keeps original date and cannot override an instrument price',
    () {
      final quote = ShadowMarketSnapshot.fromJson(fixture(2)).rows[1];
      const saved = AppDocument(
        id: 'old-id',
        data: {
          'c_name': 'Company B',
          'pa': '19.75',
          'date': '2026-10-27T12:00:00Z',
        },
      );
      final now = DateTime.parse('2026-10-28T12:05:00Z'),
          expired = DateTime.parse('2026-10-28T12:10:00Z');
      expect(quote.displayPriceAt(now, lastKnown: saved), '21.25');
      expect(quote.displayPriceAt(expired, lastKnown: saved), '19.75');
      expect(
        quote.displayPriceBasisAt(expired, lastKnown: saved),
        'RECOVERED_LAST_KNOWN',
      );
      expect(quote.priceAt(expired), isNull);
      const future = AppDocument(
        id: 'future',
        data: {
          'c_name': 'Company B',
          'pa': '19.75',
          'date': '2026-10-29T12:00:00Z',
        },
      );
      expect(quote.displayPriceAt(expired, lastKnown: future), isNull);
    },
  );
  test(
    'v2 rejects invented trade dates, authority, invalid prices and unbounded cache',
    () {
      final invalid = <String, Object>{
        'price_decimal': true,
        'source_event_at': '2026-10-28T12:00:00Z',
        'reported_day': '2026-10-28',
        'prediction_eligible': true,
        'portfolio_valuation_eligible': true,
        'captured_at': '2026-10-28T12:01:00Z',
        'expires_at': '2026-10-28T14:00:00Z',
      };
      for (final entry in invalid.entries) {
        final data = fixture(2);
        data['rows'][1]['reference_price'][entry.key] = entry.value;
        expect(
          () => ShadowMarketSnapshot.fromJson(data),
          throwsA(isA<BackendFailure>()),
        );
      }
    },
  );
  test('exact preview decimals and missing values stay separate', () {
    final snapshot = ShadowMarketSnapshot.fromJson(fixture());
    expect(
      snapshot.rows[0].priceAt(DateTime.parse('2026-10-28T12:05:00Z')),
      '10.50000000000000000001',
    );
    expect(
      snapshot.rows[1].priceAt(DateTime.parse('2026-10-28T12:05:00Z')),
      isNull,
    );
  });
  test('cached preview expires and never leaks future captures', () {
    final quote = ShadowMarketSnapshot.fromJson(fixture()).rows.first;
    expect(quote.priceAt(DateTime.parse('2026-10-28T12:20:00Z')), isNull);
    expect(quote.priceAt(DateTime.parse('2026-10-28T11:59:59Z')), isNull);
  });
  test('numeric coercion and excess precision cannot pass maximum price', () {
    for (final price in ['1000000000000.00000000001', '0', 'NaN', true, 10.5]) {
      final data = fixture();
      data['rows'][0]['price_decimal'] = price;
      expect(
        () => ShadowMarketSnapshot.fromJson(data),
        throwsA(isA<BackendFailure>()),
      );
    }
  });
  test('invalid calendar and naive timestamps rejected', () {
    for (final stamp in ['2026-02-30T12:00:00Z', '2026-10-28T12:00:00']) {
      final data = fixture();
      data['rows'][0]['captured_at'] = stamp;
      expect(
        () => ShadowMarketSnapshot.fromJson(data),
        throwsA(isA<BackendFailure>()),
      );
    }
  });
  test('no unavailable prices or prediction authority', () {
    final data = fixture();
    data['rows'][1]['price_decimal'] = '5.00';
    expect(
      () => ShadowMarketSnapshot.fromJson(data),
      throwsA(isA<BackendFailure>()),
    );
    final promoted = fixture();
    promoted['rows'][0]['prediction_eligible'] = true;
    expect(
      () => ShadowMarketSnapshot.fromJson(promoted),
      throwsA(isA<BackendFailure>()),
    );
  });
  test('empty disabled feed is explicit and duplicates are rejected', () {
    final data = fixture();
    data['rows'] = [];
    data['status'] = 'DISABLED';
    expect(ShadowMarketSnapshot.fromJson(data).rows, isEmpty);
    final duplicate = fixture();
    duplicate['rows'].add(duplicate['rows'][0]);
    expect(
      () => ShadowMarketSnapshot.fromJson(duplicate),
      throwsA(isA<BackendFailure>()),
    );
  });
  test('RPC errors never reveal remote details', () async {
    final client = ShadowMarketFeedClient.withReader(
      () async => throw Exception('private-response'),
    );
    await expectLater(
      client.read(),
      throwsA(
        isA<BackendFailure>().having(
          (e) => e.message,
          'message',
          isNot(contains('private-response')),
        ),
      ),
    );
    final valid = ShadowMarketFeedClient.withReader(() async => fixture());
    expect((await valid.read()).rows.length, 2);
  });
}
