/// Shared financial settings; mirrors the PHP application.
const double kCommissionRate = 0.01;
const double kTaxRate = 0.10;

class BackendFailure implements Exception {
  final String message;
  final bool signedOut;
  const BackendFailure(this.message, {this.signedOut = false});
  @override
  String toString() => message;
}

class AppUser {
  final String id;
  final String email;
  const AppUser({required this.id, required this.email});
}

class AppDocument {
  final String id;
  final Map<String, dynamic> data;
  const AppDocument({required this.id, required this.data});
}

class DocumentPage {
  final List<AppDocument> documents;
  const DocumentPage(this.documents);
}

enum SignUpOutcome { signedIn, confirmationRequired }

enum EmailLinkOutcome { confirmed, passwordRecovery }

/// Optional email flows; separate from ordinary application data access.
abstract interface class EmailAuthBackend {
  bool get emailLinksEnabled;
  bool get hasRecoverySession;
  Future<void> requestPasswordReset(String email);
  Future<void> resendConfirmation(String email);
  Future<EmailLinkOutcome> completeEmailLink(Uri uri);
  Future<void> updateRecoveredPassword(String password);
  Future<void> cancelEmailRecovery();
}

/// Optional current display only; historical and portfolio methods stay separate.
abstract interface class MarketDisplayBackend {
  bool get marketDisplayEnabled;
  Future<Object?> readMarketDisplay();
}

abstract interface class AppBackend {
  Future<AppUser> restoreUser();
  Future<AppUser> getUser();
  Future<void> signIn({
    required String email,
    required String password,
    required bool remember,
  });
  Future<SignUpOutcome> signUp({
    required String email,
    required String password,
    required String name,
    required bool remember,
  });
  Future<void> signOut();
  Future<DocumentPage> listDocuments({
    required String collectionId,
    List<String> queries = const [],
  });
  Future<void> recordTrade({
    required String requestId,
    required bool isBuy,
    required String company,
    required String quantity,
    required String price,
  });
}
