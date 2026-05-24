import 'package:flutter/material.dart';
import '../appwrite_client.dart';
import 'screener.dart';
import 'portfolio.dart';
import 'statistics.dart';
import 'login.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _idx = 0;
  final _pages = const [ScreenerScreen(), PortfolioScreen(), StatisticsScreen()];

  Future<void> _logout() async {
    await account.deleteSession(sessionId: 'current');
    if (!mounted) return;
    Navigator.pushReplacement(context,
      MaterialPageRoute(builder: (_) => const LoginScreen()));
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('myInterpreter'),
      actions: [IconButton(icon: const Icon(Icons.logout), onPressed: _logout)],
    ),
    body: _pages[_idx],
    bottomNavigationBar: NavigationBar(
      selectedIndex: _idx,
      onDestinationSelected: (i) => setState(() => _idx = i),
      destinations: const [
        NavigationDestination(icon: Icon(Icons.search), label: 'Screener'),
        NavigationDestination(icon: Icon(Icons.account_balance_wallet), label: 'Portfolio'),
        NavigationDestination(icon: Icon(Icons.bar_chart), label: 'Stats'),
      ],
    ),
  );
}
