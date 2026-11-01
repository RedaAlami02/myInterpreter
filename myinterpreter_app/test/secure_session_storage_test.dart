import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/secure_session_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));
  test(
    'remember setting survives a new storage instance and isolates projects',
    () async {
      final first = SecureSessionStorage('project-a');
      await first.setRemember(true);
      await first.persistSession('fixture-session');
      expect(
        await SecureSessionStorage('project-a').accessToken(),
        'fixture-session',
      );
      expect(await SecureSessionStorage('project-b').accessToken(), isNull);
    },
  );
  test(
    'queued persistence cannot resurrect credentials after opting out',
    () async {
      final store = SecureSessionStorage('project-a');
      await store.setRemember(true);
      await Future.wait([
        store.persistSession('old-fixture'),
        store.setRemember(false),
        store.persistSession('late-fixture'),
      ]);
      expect(await store.hasAccessToken(), isFalse);
      expect(await store.storage.read(key: store.sessionKey), isNull);
      expect(await SecureSessionStorage('project-a').accessToken(), isNull);
    },
  );
}
