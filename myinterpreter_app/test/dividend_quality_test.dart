import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/dividends.dart';

void main() {
  final fixtures =
      jsonDecode(
            File('../tests/fixtures/dividend_periods.json').readAsStringSync(),
          )
          as List<dynamic>;
  for (final fixture in fixtures.cast<Map<String, dynamic>>()) {
    test(fixture['name'] as String, () {
      final source = Map<String, dynamic>.from(fixture['row'] as Map);
      final before = jsonEncode(source);
      final dividend = Dividend.fromDoc(source);
      expect(dividend.verificationIssue, fixture['issue']);
      expect(jsonEncode(source), before);
      if (fixture['issue'] != null) {
        expect(dividend.confirmed, isFalse);
        expect(dividend.amount, isNull);
        expect(dividend.exDate, isNull);
        expect(dividend.payDate, isNull);
        expect(dividend.payDateEnd, isNull);
        expect(dividend.yieldOn(100), isNull);
        expect(forecastExDate([dividend], 2028), isNull);
      } else {
        expect(dividend.confirmed, source['confirmed'] == true);
        expect(dividend.amount, source['amount']);
        expect(dividend.payDate, source['pay_date']);
      }
    });
  }
}
