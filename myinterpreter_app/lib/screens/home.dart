import 'package:flutter/material.dart';
import '../appwrite_client.dart';
import 'screener.dart';
import 'portfolio.dart';
import 'statistics.dart';
import 'dividends.dart';
import 'login.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _idx = 0;

  // IndexedStack rather than swapping the child: each tab keeps its scroll
  // position and its already-loaded data, so switching back does not refetch.
  final _pages = const [
    ScreenerScreen(),
    PortfolioScreen(),
    DividendsScreen(),
    StatisticsScreen(),
  ];
  static const _titles = ['Screener', 'Portefeuille', 'Dividendes', 'Statistiques'];

  Future<void> _logout() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Se déconnecter ?'),
        content: const Text('Vous devrez saisir vos identifiants à nouveau.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Annuler')),
          TextButton(onPressed: () => Navigator.pop(ctx, true),  child: const Text('Déconnexion')),
        ],
      ),
    );
    if (ok != true) return;
    await account.deleteSession(sessionId: 'current');
    if (!mounted) return;
    Navigator.pushReplacement(context,
      MaterialPageRoute(builder: (_) => const LoginScreen()));
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(_titles[_idx]),
      actions: [IconButton(icon: const Icon(Icons.logout), onPressed: _logout)],
    ),
    body: SafeArea(child: IndexedStack(index: _idx, children: _pages)),
    bottomNavigationBar: NavigationBar(
      selectedIndex: _idx,
      onDestinationSelected: (i) => setState(() => _idx = i),
      destinations: const [
        NavigationDestination(
          icon: Icon(Icons.search_outlined),
          selectedIcon: Icon(Icons.search),
          label: 'Screener'),
        NavigationDestination(
          icon: Icon(Icons.account_balance_wallet_outlined),
          selectedIcon: Icon(Icons.account_balance_wallet),
          label: 'Portefeuille'),
        NavigationDestination(
          icon: Icon(Icons.savings_outlined),
          selectedIcon: Icon(Icons.savings),
          label: 'Dividendes'),
        NavigationDestination(
          icon: Icon(Icons.bar_chart_outlined),
          selectedIcon: Icon(Icons.bar_chart),
          label: 'Stats'),
      ],
    ),
  );
}
