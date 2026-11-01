import 'package:myinterpreter_app/backend_contract.dart';

class FakeBackend implements AppBackend {
  bool signedIn = false;
  bool? lastRemember;
  SignUpOutcome registration = SignUpOutcome.confirmationRequired;
  bool failFirstTrade = false;
  final trades = <Map<String, String>>[];
  @override
  Future<AppUser> restoreUser() => getUser();
  @override
  Future<AppUser> getUser() async {
    if (!signedIn) throw const BackendFailure('Please sign in again.');
    return const AppUser(id: 'fixture-user', email: 'fixture@example.invalid');
  }

  @override
  Future<void> signIn({
    required String email,
    required String password,
    required bool remember,
  }) async {
    signedIn = true;
    lastRemember = remember;
  }

  @override
  Future<SignUpOutcome> signUp({
    required String email,
    required String password,
    required String name,
    required bool remember,
  }) async {
    lastRemember = remember;
    signedIn = registration == SignUpOutcome.signedIn;
    return registration;
  }

  @override
  Future<void> signOut() async {
    signedIn = false;
  }

  @override
  Future<DocumentPage> listDocuments({
    required String collectionId,
    List<String> queries = const [],
  }) async => const DocumentPage([]);
  @override
  Future<void> recordTrade({
    required String requestId,
    required bool isBuy,
    required String company,
    required String quantity,
    required String price,
  }) async {
    trades.add({'id': requestId, 'quantity': quantity, 'price': price});
    if (failFirstTrade && trades.length == 1) {
      throw const BackendFailure(
        'Uncertain response. Retry the same submission.',
      );
    }
  }
}
