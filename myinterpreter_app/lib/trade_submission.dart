import 'dart:math';
import 'backend_contract.dart';
import 'portfolio_changes.dart';

String newTradeRequestId() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  final value = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  return '${value.substring(0, 8)}-${value.substring(8, 12)}-${value.substring(12, 16)}-${value.substring(16, 20)}-${value.substring(20)}';
}

/// Keep one request identity and immutable payload across uncertain responses.
/// A changed payload needs a deliberate new submission after checking holdings.
class TradeSubmission {
  final String requestId;
  final bool isBuy;
  final String company;
  final String quantity;
  final String price;
  bool _notified = false;
  TradeSubmission({
    required this.isBuy,
    required this.company,
    required this.quantity,
    required this.price,
    String? requestId,
  }) : requestId = requestId ?? newTradeRequestId();

  bool matches({required String quantity, required String price}) =>
      this.quantity == quantity && this.price == price;

  Future<void> submit(AppBackend backend) async {
    await backend.recordTrade(
      requestId: requestId,
      isBuy: isBuy,
      company: company,
      quantity: quantity,
      price: price,
    );
    if (!_notified) {
      _notified = true;
      portfolioChanges.tradeConfirmed();
    }
  }
}
