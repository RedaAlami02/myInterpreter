import 'package:flutter/material.dart';
import 'package:appwrite/appwrite.dart';
import 'appwrite_client.dart';
import 'screens/login.dart';
import 'screens/home.dart';

void main() => runApp(const MyApp());

class MyApp extends StatelessWidget {
  const MyApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'myInterpreter',
    theme: ThemeData(useMaterial3: true, colorSchemeSeed: Colors.indigo),
    home: const _AuthGate(),
  );
}

class _AuthGate extends StatelessWidget {
  const _AuthGate();
  @override
  Widget build(BuildContext context) => FutureBuilder(
    future: account.get(),
    builder: (ctx, snap) {
      if (snap.connectionState != ConnectionState.done) {
        return const Scaffold(body: Center(child: CircularProgressIndicator()));
      }
      if (snap.hasError && snap.error is AppwriteException) return const LoginScreen();
      if (snap.hasData) return const HomeScreen();
      return const LoginScreen();
    },
  );
}
