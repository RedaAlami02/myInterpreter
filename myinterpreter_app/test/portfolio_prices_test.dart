import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/portfolio_prices.dart';

void main() {
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
