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

class _AuthGate extends StatefulWidget {
  const _AuthGate();
  @override
  State<_AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<_AuthGate> {
  late final Future _future = _checkAuth();

  Future _checkAuth() async {
    try {
      print('DEBUG auth: checking session...');
      final me = await account.get();
      print('DEBUG auth: logged in as ${me.$id}');
      return me;
    } catch (e) {
      print('DEBUG auth: not logged in — $e');
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder(
    future: _future,
    builder: (ctx, snap) {
      if (snap.connectionState != ConnectionState.done) {
        return const Scaffold(body: Center(child: CircularProgressIndicator()));
      }
      if (snap.hasError) return const LoginScreen();
      if (snap.hasData) return const HomeScreen();
      return const LoginScreen();
    },
  );
}
