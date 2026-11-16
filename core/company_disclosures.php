<?php
// Reviewed public filings; units and audit trail: docs/T2S_DATA_REVIEW.md.
// Interim earnings must never replace annual earnings in valuation ratios.
function reviewed_company_disclosure(string $symbol): ?array
{
    if ($symbol !== 'T2S') return null;
    $shares = 22584118;
    $profit = 204.576;
    $equity = 1410404000;
    return [
        'name' => 'T2S Group Holding',
        'fields' => [
            'fiscal_year' => 2025, 'fy_est' => null, 'rnpg_est' => null,
            'na' => $shares, 'bpa' => round($profit * 1e6 / $shares, 2),
            'cp' => $equity, 'roe' => round($profit * 1e6 / $equity * 100, 2),
            'revenue' => 1763.333, 'net_profit' => $profit,
            'ebitda' => 388.402, 'ebit' => 381.212,
            'net_debt' => 222.346, 'net_cash' => 202.821,
            'total_assets' => 3271.222, 'fcf' => 292.301,
            'profit_margin' => round($profit / 1763.333 * 100, 2),
            'sector' => 'Santé',
            'description' => "Fondé en 1992 à Casablanca, T2S Group fournit des solutions de technologie médicale : équipements, diagnostic, maintenance et systèmes numériques pour les professionnels de santé. Le groupe exerce au Maroc et en Afrique subsaharienne et est coté depuis juillet 2026.",
        ],
        'charts' => [
            'ca' => ['2023' => 1373.642, '2024' => 1507.945, '2025' => 1763.333],
            'rnpg' => ['2023' => 74.937, '2024' => 67.311, '2025' => 204.576],
            'ebe' => ['2023' => 245.850, '2024' => 275.748, '2025' => 388.402],
            'fp' => ['2025' => 1410.404], 'ebit' => ['2025' => 381.212],
            'dn' => ['2025' => 222.346], 'fcf' => ['2025' => 292.301],
        ],
        'shareholders_as_of' => '2026-07-27',
        'shareholders' => [
            ['name' => 'Trone Investment Holdings Limited', 'pct' => 42.1],
            ['name' => 'Abderraouf SORDO', 'pct' => 19.4],
            ['name' => 'Ahmed ACHAACH', 'pct' => 7.1],
            ['name' => 'Ismail BOUIH', 'pct' => 3.1],
            ['name' => 'Mohamed BOUZID', 'pct' => 2.5],
            ['name' => 'Youssef BENABUD', 'pct' => 1.2],
            ['name' => 'Autres actionnaires', 'pct' => 2.0],
            ['name' => 'Flottant', 'pct' => 22.6],
        ],
        'interim' => [
            ['period' => 'S1 2025', 'revenue' => 773, 'ebitda' => 170, 'net_profit' => 109],
            ['period' => 'S1 2026', 'revenue' => 978, 'ebitda' => 243, 'net_profit' => 91],
        ],
    ];
}

function apply_reviewed_disclosure(string $symbol, array $data): array
{
    $reviewed = reviewed_company_disclosure($symbol);
    if ($reviewed === null) return $data;
    unset($data['error']);
    $data['symbol'] = $symbol;
    $data['ext_name'] = $data['ext_name'] ?? $reviewed['name'];
    $data['description'] = ($data['description'] ?? null) ?: $reviewed['fields']['description'];
    $data['sector'] = 'Santé';
    $latest = 0;
    foreach (array_keys($data['charts']['rnpg'] ?? []) as $year) {
        if (preg_match('/^\d{4}$/', (string)$year)) $latest = max($latest, (int)$year);
    }
    foreach ($reviewed['charts'] as $metric => $series) {
        $data['charts'][$metric] = array_replace($data['charts'][$metric] ?? [], $series);
        foreach (array_keys($series) as $year) unset($data['charts'][$metric][$year . 'p']);
        ksort($data['charts'][$metric]);
    }
    // Historical corrections must not freeze newer reported accounts.
    if ($latest <= 2025) {
        $fields = $reviewed['fields'];
        unset($fields['fy_est'], $fields['rnpg_est'], $fields['sector'], $fields['description']);
        $data['computed'] = array_replace($data['computed'] ?? [], $fields);
    }
    if (empty($data['shareholders'])) {
        $data['shareholders'] = $reviewed['shareholders'];
        $data['shareholders_as_of'] = $reviewed['shareholders_as_of'];
    }
    $data['interim'] = $reviewed['interim'];
    return $data;
}
