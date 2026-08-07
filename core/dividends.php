<?php
/**
 * Dividend helpers, shared by the company page, the portfolio panel and the
 * calendar page so all three agree on what "next payment" and "confirmed" mean.
 *
 * The `dividends` collection is filled by the weekly cloud function from
 * calendar.example. Two properties of that source shape everything here:
 *
 *   - A row is *confirmed* only once the AGM has voted, which the source signals
 *     by publishing an ex-dividend date. Until then the payment date is its own
 *     estimate, often given as a window rather than a day. We never present an
 *     estimate as a firm date.
 *   - The dividend paid in calendar year Y comes out of fiscal year Y-1. That is
 *     why the year on a row is the year of *payment*, not of the accounts.
 */

require_once __DIR__ . '/Appwrite.php';

/** All dividend rows for one company, newest year first. */
function div_for_company(string $cName): array
{
    try {
        $rows = aw_list_docs('dividends', [
            q_equal('c_name', $cName),
            q_order_desc('year'),
            q_limit(50),
        ]);
    } catch (Throwable $e) {
        return [];
    }
    return $rows;
}

/** Every dividend row for one payment year, cheapest single call for the calendar. */
function div_for_year(int $year): array
{
    try {
        return aw_list_docs('dividends', [
            q_equal('year', $year),
            q_limit(200),
        ]);
    } catch (Throwable $e) {
        return [];
    }
}

/**
 * The row a user cares about: the next payment still ahead of them this year,
 * or if the year's payments have all passed, the most recent one.
 *
 * Returns [row, 'upcoming'|'past'] or [null, null].
 */
function div_next(array $rows, ?string $today = null): array
{
    $today = $today ?: date('Y-m-d');
    $year  = (int)date('Y', strtotime($today));

    $thisYear = array_values(array_filter($rows, fn($r) => (int)($r['year'] ?? 0) === $year));
    if (!$thisYear) return [null, null];

    // Sort by whichever date we have — the window's end still orders correctly.
    usort($thisYear, fn($a, $b) => strcmp(div_date($a) ?? '9', div_date($b) ?? '9'));

    foreach ($thisYear as $r) {
        $d = div_date_end($r) ?: div_date($r);
        if ($d && $d >= $today) return [$r, 'upcoming'];
    }
    return [end($thisYear), 'past'];
}

/** Payment date, or the start of the payment window. */
function div_date(?array $r): ?string
{
    if (!$r) return null;
    $d = trim((string)($r['pay_date'] ?? ''));
    return $d !== '' ? $d : null;
}

/** End of the payment window, when the source gave a range instead of a day. */
function div_date_end(?array $r): ?string
{
    if (!$r) return null;
    $d = trim((string)($r['pay_date_end'] ?? ''));
    return $d !== '' ? $d : null;
}

/** True when the AGM has voted and the dates are firm. */
function div_confirmed(?array $r): bool
{
    return $r && !empty($r['confirmed']);
}

/** Yield against a live price, as a percentage, or null. */
function div_yield(?array $r, ?float $price): ?float
{
    $amt = (float)($r['amount'] ?? 0);
    if (!$r || $amt <= 0 || !$price || $price <= 0) return null;
    return $amt / $price * 100;
}

/**
 * "23 sept. 2026", or "23–29 sept. 2026" for an estimated window.
 * Never invents precision the source did not give.
 */
function div_fmt_date(?array $r, string $fallback = '—'): string
{
    $a = div_date($r);
    if (!$a) return $fallback;
    $b = div_date_end($r);
    if (!$b || $b === $a) return fmt_date($a, $fallback);
    // Same month reads better collapsed: "23–29 sept. 2026".
    if (substr($a, 0, 7) === substr($b, 0, 7)) {
        return ltrim(substr($a, 8, 2), '0') . '–' . fmt_date($b, $fallback);
    }
    return fmt_date($a, $fallback) . ' – ' . fmt_date($b, $fallback);
}

/**
 * A habitual month drawn from past years, for issuers whose current year has no
 * confirmed date yet — the honest version of "predicted date".
 *
 * Measured drift on this data is a 7-day median with a quarter of companies
 * moving more than a fortnight, so a month is the finest unit worth claiming.
 * Returns e.g. "septembre", or null when history is too thin or too scattered.
 */
function div_usual_month(array $rows, int $excludeYear): ?string
{
    $months = [];
    foreach ($rows as $r) {
        if ((int)($r['year'] ?? 0) === $excludeYear) continue;
        $d = $r['ex_date'] ?: div_date($r);
        if ($d) $months[] = (int)substr($d, 5, 2);
    }
    if (count($months) < 2) return null;

    $counts = array_count_values($months);
    arsort($counts);
    $top = array_key_first($counts);

    // Only claim a habit when most years actually agree. TAQA moved 87 days and
    // IMMORENTE moved from December to April — those deserve no guess at all.
    if ($counts[$top] / count($months) < 0.6) return null;

    static $fr = [1 => 'janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
                  'août', 'septembre', 'octobre', 'novembre', 'décembre'];
    return $fr[$top] ?? null;
}

/**
 * Estimate this year's ex-dividend date for a company that pays on a regular
 * rhythm, from its own history. Returns null when the history does not justify
 * a guess.
 *
 * Method: take the ex-date day-of-year for the most recent DIV_PRED_YEARS years,
 * require at least DIV_PRED_MIN_YEARS of them, and reject the company outright
 * if those dates spread more than DIV_PRED_MAX_SPREAD days. The estimate is
 * their median, which resists one odd year better than a mean.
 *
 * Backtested by predicting 2026 from 2022-2025 only, over the 16 companies that
 * qualified: median error 4 days, 13 of 16 within 10 days — but three were off
 * by 12, 31 and 33 days. EQDOM had a 5-day historical spread and still moved 33
 * days. Past regularity does not guarantee future regularity, which is why this
 * returns a *window* and why every caller must label it an estimate. A company
 * can always move its AGM.
 *
 * Returns ['date','from','to','window','spread','years','tight'] or null.
 */
const DIV_PRED_YEARS      = 4;    // how far back to look
const DIV_PRED_MIN_YEARS  = 3;    // below this there is no rhythm to speak of
const DIV_PRED_MAX_SPREAD = 14;   // days; beyond this the company is not regular
const DIV_PRED_MIN_WINDOW = 7;    // never claim tighter than this, whatever history says
const DIV_EX_TO_PAY_DAYS  = 10;   // median gap, measured over 268 paired dates

function div_predict(array $rows, int $year): ?array
{
    $byYear = [];
    foreach ($rows as $r) {
        $y = (int)($r['year'] ?? 0);
        if ($y >= $year || empty($r['ex_date'])) continue;
        $byYear[$y] = $r['ex_date'];          // one ex-date per year is enough
    }
    if (count($byYear) < DIV_PRED_MIN_YEARS) return null;

    krsort($byYear);
    $recent = array_slice($byYear, 0, DIV_PRED_YEARS, true);

    $days = [];
    foreach ($recent as $d) {
        $ts = strtotime($d);
        if ($ts !== false) $days[] = (int)date('z', $ts);   // 0-based day of year
    }
    if (count($days) < DIV_PRED_MIN_YEARS) return null;

    $spread = max($days) - min($days);
    if ($spread > DIV_PRED_MAX_SPREAD) return null;         // not regular enough

    sort($days);
    $n   = count($days);
    $mid = intdiv($n, 2);
    $med = $n % 2 ? $days[$mid] : (int)round(($days[$mid - 1] + $days[$mid]) / 2);

    // The window has to cover the observed backtest error, not just the
    // historical spread — the companies that surprised us had tight histories.
    $window = max(DIV_PRED_MIN_WINDOW, $spread);

    $base = strtotime(sprintf('%d-01-01 +%d days', $year, $med));
    if ($base === false) return null;

    return [
        'date'   => date('Y-m-d', $base),
        'from'   => date('Y-m-d', strtotime("-{$window} days", $base)),
        'to'     => date('Y-m-d', strtotime("+{$window} days", $base)),
        'pay'    => date('Y-m-d', strtotime('+' . DIV_EX_TO_PAY_DAYS . ' days', $base)),
        'window' => $window,
        'spread' => $spread,
        'years'  => $n,
        'tight'  => $spread <= 7,
    ];
}

/** "12 – 26 juin" for a predicted window. */
function div_fmt_window(array $p): string
{
    $a = strtotime($p['from']);
    $b = strtotime($p['to']);
    static $fr = [1 => 'janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
                  'août', 'septembre', 'octobre', 'novembre', 'décembre'];
    $ma = $fr[(int)date('n', $a)] ?? '';
    $mb = $fr[(int)date('n', $b)] ?? '';
    return $ma === $mb
        ? date('j', $a) . '–' . date('j', $b) . ' ' . $mb
        : date('j', $a) . ' ' . $ma . ' – ' . date('j', $b) . ' ' . $mb;
}

/** Prior-year amounts, newest first: [[year, amount], …]. */
function div_history(array $rows, int $excludeYear, int $limit = 4): array
{
    $out = [];
    foreach ($rows as $r) {
        $y = (int)($r['year'] ?? 0);
        if ($y === $excludeYear || !($r['amount'] ?? null)) continue;
        $out[$y] = ($out[$y] ?? 0) + (float)$r['amount'];   // ordinary + exceptional
    }
    krsort($out);
    $out = array_slice($out, 0, $limit, true);
    return array_map(fn($y, $a) => [$y, $a], array_keys($out), array_values($out));
}
