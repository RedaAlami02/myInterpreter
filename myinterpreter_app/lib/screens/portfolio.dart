import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:appwrite/appwrite.dart';
import '../appwrite_client.dart';
import '../main.dart' show kAccent, kBorder, kNegative, kPositive, kSurface, kSurfaceHigh, kTextMuted, kTextPrimary;
import 'buy_sell_sheet.dart';

class PortfolioScreen extends StatefulWidget {
  const PortfolioScreen({super.key});
  @override
  State<PortfolioScreen> createState() => _PortfolioScreenState();
}

class _PortfolioScreenState extends State<PortfolioScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    try {
      final me = await account.get();
      final portRes = await databases.listDocuments(
        databaseId: dbId,
        collectionId: 'portefeuille',
        queries: [Query.equal('user_id', me.$id), Query.limit(200)],
      );
      final dataRes = await databases.listDocuments(
        databaseId: dbId,
        collectionId: 'data',
        queries: [Query.orderDesc('date'), Query.limit(500)],
      );
      final prices = <String, double>{};
      for (final d in dataRes.documents) {
        final name = d.data['c_name'] as String?;
        final pa = (d.data['pa'] as num?)?.toDouble();
        if (name != null && pa != null && !prices.containsKey(name)) {
          prices[name] = pa;
        }
      }
      return {
        'holdings': portRes.documents.map((d) => d.data).toList(),
        'prices': prices,
      };
    } catch (e, st) {
      print('DEBUG portfolio ERROR: $e');
      print('DEBUG portfolio STACK: $st');
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<Map<String, dynamic>>(
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

      final holdings = snap.data!['holdings'] as List<Map<String, dynamic>>;
      final prices = snap.data!['prices'] as Map<String, double>;

      if (holdings.isEmpty) {
        return Center(
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            const Icon(Icons.account_balance_wallet_outlined, size: 48, color: kTextMuted),
            const SizedBox(height: 12),
            Text('No holdings yet', style: GoogleFonts.inter(color: kTextMuted, fontSize: 15)),
          ]),
        );
      }

      // Compute totals
      double totalInvested = 0, totalCurrent = 0;
      for (final r in holdings) {
        final qty = (r['quantity'] as num?)?.toDouble() ?? 0;
        final cost = (r['total_cost'] as num?)?.toDouble() ?? 0;
        final pa = prices[r['c_name'] as String? ?? ''];
        totalInvested += cost;
        if (pa != null) totalCurrent += qty * pa;
      }
      final totalPnl = totalCurrent - totalInvested;
      final hasPrices = totalCurrent > 0;

      return RefreshIndicator(
        color: kAccent,
        onRefresh: () {
          setState(() => _future = _load());
          return _future;
        },
        child: ListView(
          padding: const EdgeInsets.only(top: 8, bottom: 16),
          children: [
            // ── Summary card ─────────────────────────────────────────────
            Container(
              margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: kSurfaceHigh,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: kBorder),
              ),
              child: Row(children: [
                _summaryCol('Invested', '${totalInvested.toStringAsFixed(0)} MAD', kTextMuted),
                _vDivider(),
                _summaryCol('Current',
                  hasPrices ? '${totalCurrent.toStringAsFixed(0)} MAD' : '—', kTextPrimary),
                _vDivider(),
                _summaryCol(
                  totalPnl >= 0 ? 'Gain' : 'Loss',
                  hasPrices
                      ? '${totalPnl >= 0 ? '+' : ''}${totalPnl.toStringAsFixed(0)} MAD'
                      : '—',
                  hasPrices ? (totalPnl >= 0 ? kPositive : kNegative) : kTextMuted,
                ),
              ]),
            ),
            const SizedBox(height: 4),
            // ── Per-holding cards ─────────────────────────────────────────
            ...holdings.map((r) {
              final name = r['c_name'] as String? ?? '?';
              final qty = (r['quantity'] as num?)?.toDouble() ?? 0;
              final cost = (r['total_cost'] as num?)?.toDouble() ?? 0;
              final avgBuy = qty > 0 ? cost / qty : 0.0;
              final pa = prices[name];

              final pnl = pa != null ? (qty * pa) - cost : null;
              final pnlPct = (pnl != null && cost > 0) ? (pnl / cost) * 100 : null;
              final isGain = pnl != null && pnl >= 0;
              final pnlColor = pnl == null ? kTextMuted : (isGain ? kPositive : kNegative);

              return Container(
                margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                decoration: BoxDecoration(
                  color: kSurface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: kBorder),
                ),
                child: Column(children: [
                  // Row 1: name + % change
                  Row(children: [
                    Expanded(
                      child: Text(name, style: GoogleFonts.inter(
                        color: kTextPrimary, fontSize: 14, fontWeight: FontWeight.w600)),
                    ),
                    Text(
                      pnlPct != null
                          ? '${pnlPct >= 0 ? '+' : ''}${pnlPct.toStringAsFixed(2)}%'
                          : '—',
                      style: GoogleFonts.inter(
                        color: pnlColor, fontSize: 13, fontWeight: FontWeight.w700),
                    ),
                  ]),
                  const SizedBox(height: 6),
                  // Row 2: qty + P&L amount
                  Row(children: [
                    Expanded(
                      child: Text(
                        '${qty.toStringAsFixed(0)} shares',
                        style: GoogleFonts.inter(color: kTextMuted, fontSize: 12),
                      ),
                    ),
                    Text(
                      pnl != null
                          ? '${pnl >= 0 ? '+' : ''}${pnl.toStringAsFixed(2)} MAD'
                          : '—',
                      style: GoogleFonts.inter(
                        color: pnlColor, fontSize: 13, fontWeight: FontWeight.w600),
                    ),
                  ]),
                  const SizedBox(height: 8),
                  // Row 3: avg buy → current price + sell button
                  Row(children: [
                    Expanded(
                      child: Text(
                        pa != null
                            ? 'Avg ${avgBuy.toStringAsFixed(2)} → ${pa.toStringAsFixed(2)} MAD'
                            : 'Avg ${avgBuy.toStringAsFixed(2)} MAD',
                        style: GoogleFonts.inter(color: kTextMuted, fontSize: 11),
                      ),
                    ),
                    GestureDetector(
                      onTap: () async {
                        if (name.isEmpty) return;
                        await showBuySellSheet(context, name, avgBuy, isBuy: false);
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
                  ]),
                ]),
              );
            }),
          ],
        ),
      );
    },
  );

  Widget _summaryCol(String label, String value, Color valueColor) => Expanded(
    child: Column(children: [
      Text(label, style: GoogleFonts.inter(color: kTextMuted, fontSize: 11)),
      const SizedBox(height: 4),
      Text(value, style: GoogleFonts.inter(
        color: valueColor, fontSize: 13, fontWeight: FontWeight.w700),
        textAlign: TextAlign.center),
    ]),
  );

  Widget _vDivider() => Container(
    width: 1, height: 32, color: kBorder, margin: const EdgeInsets.symmetric(horizontal: 4));
}
