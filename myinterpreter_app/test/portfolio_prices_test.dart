import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/portfolio_prices.dart';

Map<String, dynamic> currentRow(
  DateTime now, {
  String day = '2026-11-03',
  String basis = 'REPORTED_QUOTE',
}) => {
  'c_name': 'Alpha',
  '_market_display': {
    'available': true,
    'asset_key': 'company:alpha',
    'price_basis': basis,
    'reported_day': day,
    'price_decimal': '20',
    'captured_at': now.subtract(const Duration(minutes: 1)).toIso8601String(),
    'expires_at': now.add(const Duration(minutes: 5)).toIso8601String(),
  },
};

void main() {
  final now = DateTime.utc(2026, 11, 3, 12);
  final recorded = [
    {'c_name': 'Alpha', 'pa': 10, 'date': '2026-10-21T12:00:00Z'},
    {'c_name': 'Beta', 'pa': 15, 'date': '2026-10-21T12:00:00Z'},
  ];
  test(
    'current quotes overlay display only and mixed dates suppress totals',
    () {
      final prices = portfolioDisplayPrices(recorded, [
        currentRow(now),
      ], now: now);
      expect(prices['Alpha']!.price, 20);
      expect(prices['Alpha']!.status, 'CURRENT_REPORTED_QUOTE');
      expect(recorded[0]['pa'], 10);
      expect(prices['Beta']!.day, '2026-10-21');
      final totals = portfolioReferenceTotals([
        {'c_name': 'Alpha', 'quantity': 1, 'total_cost': 5},
        {'c_name': 'Beta', 'quantity': 1, 'total_cost': 6},
      ], prices);
      expect(totals.complete, isFalse);
      expect(totals.portfolioValuationEligible, isFalse);
    },
  );
  test(
    'expired, reference and wrong-day prices never replace dated history',
    () {
      for (final row in [
        currentRow(now, day: '2026-11-02'),
        currentRow(now, basis: 'INSTRUMENT_REFERENCE'),
      ]) {
        expect(
          portfolioDisplayPrices(recorded, [row], now: now)['Alpha']!.price,
          10,
        );
      }
      expect(
        portfolioDisplayPrices(recorded, [
          currentRow(now),
        ], now: now.add(const Duration(minutes: 5)))['Alpha']!.price,
        10,
      );
    },
  );
  test('conflicting current identities suppress the price', () {
    expect(
      portfolioDisplayPrices(recorded, [
        currentRow(now),
        currentRow(now),
      ], now: now)['Alpha']!.status,
      'CONFLICT',
    );
  });
  test('Casablanca day is independent of phone timezone at local midnight', () {
    final boundary = DateTime.utc(2024, 7, 3, 23, 30);
    final old = [
      {'c_name': 'Alpha', 'pa': 10, 'date': '2000-01-01T12:00:00Z'},
    ];
    expect(
      portfolioDisplayPrices(old, [
        currentRow(boundary, day: '2024-07-04'),
      ], now: boundary)['Alpha']!.price,
      20,
    );
    expect(
      portfolioDisplayPrices(old, [
        currentRow(boundary, day: '2024-07-03'),
      ], now: boundary)['Alpha']!.price,
      10,
    );
  });

  final fixture =
      jsonDecode(
            File(
              '../tests/fixtures/portfolio/recorded_prices.json',
            ).readAsStringSync(),
          )
          as Map<String, dynamic>;
  for (final raw in fixture['cases'] as List) {
    final entry = raw as Map<String, dynamic>;
    test(entry['name'] as String, () {
      final prices = recordedPortfolioPrices(
        (entry['prices'] as List)
            .map((v) => Map<String, dynamic>.from(v as Map))
            .toList(),
        now: DateTime.parse(fixture['now'] as String),
      );
      final result = portfolioReferenceTotals(
        (entry['holdings'] as List)
            .map((v) => Map<String, dynamic>.from(v as Map))
            .toList(),
        prices,
        holdingsComplete: entry['holdings_complete'] as bool? ?? true,
      );
      final expected = entry['expected'] as Map<String, dynamic>;
      expect(result.value, expected['value']);
      expect(result.pnl, expected['pnl']);
      expect(result.complete, expected['complete']);
      expect(result.portfolioValuationEligible, isFalse);
    });
  }
}
