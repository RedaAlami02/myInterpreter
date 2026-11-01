import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../query.dart';
import '../backend.dart';
import '../dividends.dart';
import '../portfolio_prices.dart';
import '../main.dart'
    show
        kAccent,
        kBorder,
        kNegative,
        kPositive,
        kSurface,
        kSurfaceHigh,
        kTextMuted,
        kTextPrimary;
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
    final me = await backend.getUser();
    final portRes = await backend.listDocuments(
      collectionId: 'portefeuille',
      queries: [Query.equal('user_id', me.id), Query.limit(500)],
    );
    var priceRecords = <Map<String, dynamic>>[];
    try {
      final lpRes = await backend.listDocuments(
        collectionId: 'latest_prices',
        queries: [Query.limit(500)],
      );
      priceRecords = lpRes.documents.map((d) => d.data).toList();
    } catch (_) {
      // Holdings/costs remain usable without recorded market prices.
    }
    // This year's dividends, keyed by company. Best-effort: the portfolio
    // must still render if the dividend collection is unreachable.
    final divs = <String, Dividend>{};
    try {
      for (final d in await dividendsForYear(DateTime.now().year)) {
        // Keep whichever row is furthest ahead — an ordinary and an
        // exceptional dividend can both exist in the same year.
        final prev = divs[d.cName];
        if (prev == null || (d.amount ?? 0) > (prev.amount ?? 0)) {
          divs[d.cName] = d;
        }
      }
    } catch (_) {}

    return {
      'holdings': portRes.documents.map((d) => d.data).toList(),
      'priceRecords': priceRecords,
      'dividends': divs,
    };
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<Map<String, dynamic>>(
    future: _future,
    builder: (ctx, snap) {
      if (snap.hasError) {
        return Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.error_outline, size: 48, color: kNegative),
              const SizedBox(height: 12),
              Text(
                '${snap.error}',
                style: const TextStyle(color: kTextMuted),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () => setState(() => _future = _load()),
                child: const Text('Retry'),
              ),
            ],
          ),
        );
      }
      if (!snap.hasData) {
        return const Center(child: CircularProgressIndicator(color: kAccent));
      }

      final holdings = snap.data!['holdings'] as List<Map<String, dynamic>>;
      final quotes = recordedPortfolioPrices(
        snap.data!['priceRecords'] as List<Map<String, dynamic>>,
      );
      final prices = <String, double>{
        for (final entry in quotes.entries)
          if (entry.value.price != null) entry.key: entry.value.price!,
      };
      final divs = (snap.data!['dividends'] as Map<String, Dividend>?) ?? {};
      final today = todayIso();

      if (holdings.isEmpty) {
        return Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(
                Icons.account_balance_wallet_outlined,
                size: 48,
                color: kTextMuted,
              ),
              const SizedBox(height: 12),
              Text(
                'No holdings yet',
                style: GoogleFonts.inter(color: kTextMuted, fontSize: 15),
              ),
            ],
          ),
        );
      }

      final estimate = portfolioReferenceTotals(
        holdings,
        quotes,
        holdingsComplete: holdings.length < 500,
      );
      final totalPnl = estimate.pnl;

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
              child: Row(
                children: [
                  _summaryCol(
                    'Invested',
                    estimate.invested != null
                        ? '${estimate.invested!.toStringAsFixed(0)} MAD'
                        : '—',
                    kTextMuted,
                  ),
                  _vDivider(),
                  _summaryCol(
                    'Reference estimate',
                    estimate.value != null
                        ? '${estimate.value!.toStringAsFixed(0)} MAD'
                        : '—',
                    kTextPrimary,
                  ),
                  _vDivider(),
                  _summaryCol(
                    'Indicative P&L',
                    totalPnl != null
                        ? '${totalPnl >= 0 ? '+' : ''}${totalPnl.toStringAsFixed(0)} MAD'
                        : '—',
                    totalPnl != null
                        ? (totalPnl >= 0 ? kPositive : kNegative)
                        : kTextMuted,
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Text(
                estimate.complete
                    ? 'Recorded prices from ${estimate.day} (UTC). Estimates are not live quotes.'
                    : 'Recorded prices only. Totals need complete positions and prices from the same recorded date.',
                style: const TextStyle(color: kTextMuted, fontSize: 12),
              ),
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
              final pnlPct = (pnl != null && cost > 0)
                  ? (pnl / cost) * 100
                  : null;
              final isGain = pnl != null && pnl >= 0;
              final pnlColor = pnl == null
                  ? kTextMuted
                  : (isGain ? kPositive : kNegative);

              // Brokerage charges (~1% each leg) + break-even, computed on the fly.
              final fraisAchat = cost * kCommissionRate; // already paid
              final fraisVente = pa != null
                  ? (qty * pa) * kCommissionRate
                  : null; // est. on exit
              // Break-even incl. 1% commission both legs + 10% gain tax:
              //   V·(1−r−t) = B·(1+r−t)  →  V = B·(1+r−t)/(1−r−t)
              final breakeven = cost > 0
                  ? cost *
                        (1 + kCommissionRate - kTaxRate) /
                        (1 - kCommissionRate - kTaxRate)
                  : 0.0;

              return Container(
                margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                decoration: BoxDecoration(
                  color: kSurface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: kBorder),
                ),
                child: Column(
                  children: [
                    // Row 1: name + % change
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            name,
                            style: GoogleFonts.inter(
                              color: kTextPrimary,
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                        Text(
                          pnlPct != null
                              ? '${pnlPct >= 0 ? '+' : ''}${pnlPct.toStringAsFixed(2)}%'
                              : '—',
                          style: GoogleFonts.inter(
                            color: pnlColor,
                            fontSize: 13,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    // Row 2: qty + P&L amount
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '${qty.toStringAsFixed(0)} shares',
                            style: GoogleFonts.inter(
                              color: kTextMuted,
                              fontSize: 12,
                            ),
                          ),
                        ),
                        Text(
                          pnl != null
                              ? '${pnl >= 0 ? '+' : ''}${pnl.toStringAsFixed(2)} MAD'
                              : '—',
                          style: GoogleFonts.inter(
                            color: pnlColor,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    if (quotes[name]?.day != null)
                      Align(
                        alignment: Alignment.centerLeft,
                        child: Text(
                          'Recorded ${quotes[name]!.day} (UTC)',
                          style: const TextStyle(
                            color: kTextMuted,
                            fontSize: 11,
                          ),
                        ),
                      ),
                    // Row 3: avg buy → current price + sell button
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            pa != null
                                ? 'Avg ${avgBuy.toStringAsFixed(2)} → ${pa.toStringAsFixed(2)} MAD'
                                : 'Avg ${avgBuy.toStringAsFixed(2)} MAD',
                            style: GoogleFonts.inter(
                              color: kTextMuted,
                              fontSize: 11,
                            ),
                          ),
                        ),
                        GestureDetector(
                          onTap: () async {
                            if (name.isEmpty) return;
                            await showBuySellSheet(
                              context,
                              name,
                              avgBuy,
                              isBuy: false,
                            );
                            if (mounted) setState(() => _future = _load());
                          },
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 10,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: kNegative.withValues(alpha: 0.12),
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(
                                color: kNegative.withValues(alpha: 0.4),
                              ),
                            ),
                            child: const Icon(
                              Icons.sell_outlined,
                              size: 14,
                              color: kNegative,
                            ),
                          ),
                        ),
                      ],
                    ),
                    // Row 4: brokerage charges + break-even (computed ~1% each leg)
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.only(top: 8),
                      decoration: const BoxDecoration(
                        border: Border(top: BorderSide(color: kBorder)),
                      ),
                      child: Column(
                        children: [
                          _positionValueRow('Val. Achat', cost, qty),
                          _feeRow(
                            'Frais achat (1%)',
                            '${fraisAchat.toStringAsFixed(2)} MAD',
                          ),
                          _feeRow(
                            'Frais vente est. (1%)',
                            fraisVente != null
                                ? '${fraisVente.toStringAsFixed(2)} MAD'
                                : '—',
                          ),
                          _positionValueRow(
                            'Seuil équilibre',
                            breakeven,
                            qty,
                            unavailable: breakeven <= 0,
                          ),
                          // Dividend line: only when this holding actually pays, so
                          // the card does not grow a row of dashes for the rest.
                          if (divs[name]?.amount != null)
                            _dividendRow(divs[name]!, qty, today),
                        ],
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      );
    },
  );

  Widget _summaryCol(String label, String value, Color valueColor) => Expanded(
    child: Column(
      children: [
        Text(label, style: GoogleFonts.inter(color: kTextMuted, fontSize: 11)),
        const SizedBox(height: 4),
        Text(
          value,
          style: GoogleFonts.inter(
            color: valueColor,
            fontSize: 13,
            fontWeight: FontWeight.w700,
          ),
          textAlign: TextAlign.center,
        ),
      ],
    ),
  );

  Widget _vDivider() => Container(
    width: 1,
    height: 32,
    color: kBorder,
    margin: const EdgeInsets.symmetric(horizontal: 4),
  );

  /// "Dividende à venir · 60,00 MAD — 15 sept. 2026". Green when the money is
  /// still ahead of you, muted once it has been paid.
  Widget _dividendRow(Dividend d, double qty, String today) {
    final ahead = d.isUpcoming(today);
    final gross = d.amount! * qty;
    final colour = ahead ? kPositive : kTextMuted;
    return Padding(
      padding: const EdgeInsets.only(top: 3),
      child: Row(
        children: [
          Icon(
            ahead ? Icons.savings : Icons.savings_outlined,
            size: 12,
            color: colour,
          ),
          const SizedBox(width: 5),
          Expanded(
            child: Text(
              ahead
                  ? 'Dividende ${d.confirmed ? '' : 'prévu '}${fmtPayment(d)}'
                  : 'Dividende versé ${fmtPayment(d)}',
              style: GoogleFonts.inter(color: kTextMuted, fontSize: 11),
            ),
          ),
          Text(
            '${gross.toStringAsFixed(2)} MAD',
            style: GoogleFonts.inter(
              color: colour,
              fontSize: 11,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }

  Widget _positionValueRow(
    String label,
    double total,
    double quantity, {
    bool unavailable = false,
  }) => Padding(
    padding: const EdgeInsets.only(top: 3),
    child: Row(
      children: [
        Expanded(
          child: Text.rich(
            TextSpan(
              children: [
                TextSpan(text: label),
                const TextSpan(
                  text: ' (Unité)',
                  style: TextStyle(color: kTextMuted),
                ),
              ],
            ),
            style: GoogleFonts.inter(color: kTextPrimary, fontSize: 11),
          ),
        ),
        Flexible(
          child: Text.rich(
            TextSpan(
              children: [
                TextSpan(text: unavailable ? '—' : total.toStringAsFixed(2)),
                if (!unavailable && quantity > 1)
                  TextSpan(
                    text: ' (${(total / quantity).toStringAsFixed(2)})',
                    style: const TextStyle(color: kTextMuted),
                  ),
              ],
            ),
            style: GoogleFonts.inter(
              color: kTextPrimary,
              fontSize: 11,
              fontWeight: FontWeight.w500,
            ),
            textAlign: TextAlign.end,
          ),
        ),
      ],
    ),
  );

  Widget _feeRow(String label, String value) => Padding(
    padding: const EdgeInsets.only(top: 3),
    child: Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: GoogleFonts.inter(color: kTextMuted, fontSize: 11),
          ),
        ),
        Text(
          value,
          style: GoogleFonts.inter(
            color: kTextMuted,
            fontSize: 11,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    ),
  );
}
