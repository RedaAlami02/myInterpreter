import 'package:flutter/foundation.dart';

/// Invalidation only: no account IDs, holdings or tokens are cached here.
class PortfolioChanges extends ChangeNotifier {
  void tradeConfirmed() => notifyListeners();
}

final portfolioChanges = PortfolioChanges();
