import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:appwrite/appwrite.dart';
import '../appwrite_client.dart';
import '../main.dart' show kAccent, kBorder, kNegative, kSurface, kTextMuted, kTextPrimary;
import 'buy_sell_sheet.dart';

class PortfolioScreen extends StatefulWidget {
  const PortfolioScreen({super.key});
  @override
  State<PortfolioScreen> createState() => _PortfolioScreenState();
}

class _PortfolioScreenState extends State<PortfolioScreen> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<Map<String, dynamic>>> _load() async {
    try {
      print('DEBUG portfolio: getting user...');
      final me = await account.get();
      print('DEBUG portfolio: user=${me.$id}, fetching portefeuille...');
      final res = await databases.listDocuments(
        databaseId: dbId,
        collectionId: 'portefeuille',
        queries: [Query.equal('user_id', me.$id), Query.limit(200)],
      );
      print('DEBUG portfolio: got ${res.documents.length} rows');
      if (res.documents.isNotEmpty) print('DEBUG portfolio first: ${res.documents.first.data}');
      return res.documents.map((d) => d.data).toList();
    } catch (e, st) {
      print('DEBUG portfolio ERROR: $e');
      print('DEBUG portfolio STACK: $st');
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<List<Map<String, dynamic>>>(
    future: _future,
    builder: (ctx, snap) {
      if (snap.hasError) {
        return Center(
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            const Icon(Icons.error_outline, size: 48, color: kNegative),
            const SizedBox(height: 12),
            Text('${snap.error}', style: const TextStyle(color: kTextMuted), textAlign: TextAlign.center),
            const SizedBox(height: 12),
            ElevatedButton(
              onPressed: () => setState(() => _future = _load()),
              child: const Text('Retry'),
            ),
          ]),
        );
      }
      if (!snap.hasData) return const Center(child: CircularProgressIndicator(color: kAccent));
      final rows = snap.data!;
      if (rows.isEmpty) {
        return Center(
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            const Icon(Icons.account_balance_wallet_outlined, size: 48, color: kTextMuted),
            const SizedBox(height: 12),
            Text('No holdings yet', style: GoogleFonts.inter(color: kTextMuted, fontSize: 15)),
          ]),
        );
      }
      return RefreshIndicator(
        color: kAccent,
        onRefresh: () {
          setState(() => _future = _load());
          return _future;
        },
        child: ListView.builder(
          padding: const EdgeInsets.only(top: 8, bottom: 16),
          itemCount: rows.length,
          itemBuilder: (_, i) {
            final r = rows[i];
            final qty = (r['quantity'] as num?)?.toDouble() ?? 0;
            final cost = (r['total_cost'] as num?)?.toDouble() ?? 0;
            final avg = qty > 0 ? cost / qty : 0.0;
            return Container(
              margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: kSurface,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: kBorder, width: 1),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(r['c_name'] ?? '?', style: GoogleFonts.inter(
                          color: kTextPrimary, fontSize: 14, fontWeight: FontWeight.w600)),
                        const SizedBox(height: 4),
                        Text(
                          '${qty.toStringAsFixed(0)} shares  ·  avg ${avg.toStringAsFixed(2)} MAD',
                          style: GoogleFonts.inter(color: kTextMuted, fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        '${cost.toStringAsFixed(2)} MAD',
                        style: GoogleFonts.inter(
                          color: kAccent, fontSize: 14, fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 4),
                      GestureDetector(
                        onTap: () async {
                          final name = r['c_name'] as String? ?? '';
                          if (name.isEmpty) return;
                          await showBuySellSheet(context, name, avg, isBuy: false);
                          if (mounted) setState(() => _future = _load());
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            color: kNegative.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(6),
                            border: Border.all(color: kNegative.withValues(alpha: 0.4)),
                          ),
                          child: const Icon(Icons.sell_outlined, size: 14, color: kNegative),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            );
          },
        ),
      );
    },
  );
}
