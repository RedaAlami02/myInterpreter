import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/backend.dart';
import 'package:myinterpreter_app/main.dart';
import 'package:myinterpreter_app/mobile_email_auth.dart';
import 'package:myinterpreter_app/screens/login.dart';
import 'package:myinterpreter_app/screens/password_recovery.dart';

import 'support/fake_backend.dart';

class EmailBackendFixture extends FakeBackend implements EmailAuthBackend {
  @override
  bool emailLinksEnabled = true;
  @override
  bool hasRecoverySession = false;
  bool confirmation = false;
  bool updateSignedOutFailure = false;
  int callbacks = 0;
  int cancellations = 0;
  String? requested;
  String? resent;
  String? updated;

  @override
  Future<void> requestPasswordReset(String email) async => requested = email;
  @override
  Future<void> resendConfirmation(String email) async => resent = email;
  @override
  Future<EmailLinkOutcome> completeEmailLink(Uri uri) async {
    mobileAuthCode(uri);
    callbacks++;
    hasRecoverySession = !confirmation;
    return confirmation
        ? EmailLinkOutcome.confirmed
        : EmailLinkOutcome.passwordRecovery;
  }

  @override
  Future<void> updateRecoveredPassword(String password) async {
    updated = password;
    hasRecoverySession = false;
    if (updateSignedOutFailure) {
      throw const BackendFailure(
        'Signed out; server revocation unconfirmed.',
        signedOut: true,
      );
    }
  }

  @override
  Future<void> cancelEmailRecovery() async {
    cancellations++;
    hasRecoverySession = false;
  }
}

void main() {
  late AppBackend previous;
  late EmailBackendFixture fixture;
  setUp(() {
    previous = backend;
    fixture = EmailBackendFixture();
    backend = fixture;
  });
  tearDown(() => backend = previous);

  testWidgets('email actions use address and show the same neutral notice', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    await tester.enterText(
      find.byType(TextField).first,
      'fixture@example.invalid',
    );
    await tester.ensureVisible(find.text('Forgot password?'));
    await tester.tap(find.text('Forgot password?'));
    await tester.pumpAndSettle();
    expect(fixture.requested, 'fixture@example.invalid');
    expect(find.textContaining('If this address is eligible'), findsOneWidget);
    await tester.ensureVisible(find.text('Resend confirmation email'));
    await tester.tap(find.text('Resend confirmation email'));
    await tester.pumpAndSettle();
    expect(fixture.resent, 'fixture@example.invalid');
    expect(find.textContaining('If this address is eligible'), findsOneWidget);
  });

  testWidgets('disabled build hides email actions', (tester) async {
    fixture.emailLinksEnabled = false;
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    expect(find.text('Forgot password?'), findsNothing);
    expect(find.text('Resend confirmation email'), findsNothing);
  });

  testWidgets(
    'warm links route recovery once, clear stack and save matched passwords',
    (tester) async {
      final links = StreamController<Uri>.broadcast();
      addTearDown(links.close);
      await tester.pumpWidget(MyApp(emailLinkStream: links.stream));
      await tester.pumpAndSettle();
      final uri = Uri.parse('$mobileAuthCallback?code=fixture-code');
      links.add(uri);
      links.add(uri);
      await tester.pumpAndSettle();
      expect(fixture.callbacks, 1);
      expect(find.text('Set a new password'), findsOneWidget);
      expect(
        Navigator.of(
          tester.element(find.byType(PasswordRecoveryScreen)),
        ).canPop(),
        isFalse,
      );
      await tester.enterText(
        find.byType(TextField).at(0),
        'new-fixture-password',
      );
      await tester.enterText(
        find.byType(TextField).at(1),
        'different-password',
      );
      await tester.tap(find.text('Save password'));
      await tester.pumpAndSettle();
      expect(find.text('The passwords do not match.'), findsOneWidget);
      expect(fixture.updated, isNull);
      await tester.enterText(
        find.byType(TextField).at(1),
        'new-fixture-password',
      );
      await tester.tap(find.text('Save password'));
      await tester.pumpAndSettle();
      expect(fixture.updated, 'new-fixture-password');
      expect(
        find.text('Password updated. Sign in with your new password.'),
        findsOneWidget,
      );
      expect(find.widgetWithText(ElevatedButton, 'Log in'), findsOneWidget);
    },
  );

  testWidgets('cancel clears temporary session and returns to sign-in', (
    tester,
  ) async {
    fixture.hasRecoverySession = true;
    await tester.pumpWidget(
      MaterialApp(home: PasswordRecoveryScreen(auth: fixture)),
    );
    await tester.tap(find.text('Cancel recovery'));
    await tester.pumpAndSettle();
    expect(fixture.cancellations, 1);
    expect(fixture.hasRecoverySession, isFalse);
    expect(find.text('Password recovery cancelled.'), findsOneWidget);
  });

  testWidgets(
    'confirmation returns to password login without home or portfolio',
    (tester) async {
      fixture.confirmation = true;
      final links = StreamController<Uri>.broadcast();
      addTearDown(links.close);
      await tester.pumpWidget(MyApp(emailLinkStream: links.stream));
      await tester.pumpAndSettle();
      links.add(Uri.parse('$mobileAuthCallback?code=confirmation-fixture'));
      await tester.pumpAndSettle();
      expect(
        find.text('Email confirmed. Sign in with your password.'),
        findsOneWidget,
      );
      expect(fixture.signedIn, isFalse);
    },
  );

  testWidgets(
    'invalid link stays on login and never renders response details',
    (tester) async {
      final links = StreamController<Uri>.broadcast();
      addTearDown(links.close);
      await tester.pumpWidget(MyApp(emailLinkStream: links.stream));
      await tester.pumpAndSettle();
      links.add(
        Uri.parse(
          '$mobileAuthCallback?error_description=fixture-sensitive-detail',
        ),
      );
      await tester.pumpAndSettle();
      expect(find.widgetWithText(ElevatedButton, 'Log in'), findsOneWidget);
      expect(find.textContaining('Request a new link'), findsOneWidget);
      expect(find.textContaining('fixture-sensitive-detail'), findsNothing);
      expect(fixture.callbacks, 0);
    },
  );

  testWidgets('unconfirmed remote revocation still exits temporary recovery', (
    tester,
  ) async {
    fixture.hasRecoverySession = true;
    fixture.updateSignedOutFailure = true;
    await tester.pumpWidget(
      MaterialApp(home: PasswordRecoveryScreen(auth: fixture)),
    );
    await tester.enterText(
      find.byType(TextField).at(0),
      'new-fixture-password',
    );
    await tester.enterText(
      find.byType(TextField).at(1),
      'new-fixture-password',
    );
    await tester.tap(find.text('Save password'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(ElevatedButton, 'Log in'), findsOneWidget);
    expect(
      find.text('Signed out; server revocation unconfirmed.'),
      findsOneWidget,
    );
  });
}
