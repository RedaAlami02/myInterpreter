import 'dart:convert';

/// Small backend-neutral query vocabulary. The backend validates allowed fields.
abstract final class Query {
  static String equal(String field, Object? value) => jsonEncode({
    'method': 'equal',
    'attribute': field,
    'values': [value],
  });
  static String greaterThanEqual(String field, Object value) => jsonEncode({
    'method': 'greaterThanEqual',
    'attribute': field,
    'values': [value],
  });
  static String orderAsc(String field) =>
      jsonEncode({'method': 'orderAsc', 'attribute': field});
  static String orderDesc(String field) =>
      jsonEncode({'method': 'orderDesc', 'attribute': field});
  static String limit(int value) => jsonEncode({
    'method': 'limit',
    'values': [value],
  });
  static String offset(int value) => jsonEncode({
    'method': 'offset',
    'values': [value],
  });
}
