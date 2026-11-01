import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/portfolio_math.dart';

void main() {
  final fixture =
      jsonDecode(
            File(
              '../tests/fixtures/portfolio/fifo_cases.json',
            ).readAsStringSync(),
          )
          as Map<String, dynamic>;
  for (final entry in fixture['cases'] as List) {
    test(entry['name'] as String, () {
      final buys = (entry['buys'] as List)
          .map((r) => Map<String, dynamic>.from(r as Map))
          .toList();
      final sells = (entry['sells'] as List)
          .map((r) => Map<String, dynamic>.from(r as Map))
          .toList();
      final result = realizedTotals(fifoMatches(buys, sells), .01, .1);
      for (final field in ['gross', 'fees', 'tax', 'net']) {
        expect(
          result[field],
          closeTo((entry['expected'][field] as num).toDouble(), 1e-7),
        );
      }
      expect(result['unresolved_sales'], entry['expected']['unresolved_sales']);
    });
  }
}
