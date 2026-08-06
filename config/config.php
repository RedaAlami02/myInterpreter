<?php
require_once __DIR__ . '/secrets.php';
// ─── Appwrite connection constants are defined in core/Appwrite.php ───────────

// ─── App base URL — derived from the HTTP request, never from __FILE__ ────────
// Using __FILE__ or realpath() follows symlinks, giving the real filesystem path
// (e.g. /home/user/project) instead of the URL path (/myInterpreter).
// $_SERVER['SCRIPT_NAME'] is always the URL path of the originally-called script
// and is completely unaffected by symlinks.
//
// Known one-level subdirectories of the project root:
$_subdirs = ['handlers', 'core', 'config', 'assets', 'scrapping'];
$_snDir   = dirname($_SERVER['SCRIPT_NAME']); // URL dir of calling script
// e.g. /myInterpreter  (for root pages)
// e.g. /myInterpreter/handlers  (for handler pages)
if (in_array(basename($_snDir), $_subdirs, true)) {
    $_root = dirname($_snDir); // go up one more level
} else {
    $_root = $_snDir;
}
define('BASE_URL', $_root === '/' ? '' : rtrim($_root, '/'));
unset($_subdirs, $_snDir, $_root);

// ─── Admin ────────────────────────────────────────────────────────────────────
define('ADMIN_USER_ID', '6a124b8900257649d4c1');

// ─── Portfolio ────────────────────────────────────────────────────────────────
define('TAX_RATE', 0.10);   // 10 % tax applied to gross profit

// Brokerage commission — all-in ~1 % (broker + bourse + bank + TVA) charged by
// the bank on BOTH the buy and the sell, applied to the trade value.
// Single source of truth: change the rate here, or swap commission() internals
// later (e.g. a min-floor or the exact VAT breakdown) without touching call sites.
define('COMMISSION_RATE', 0.01);

function commission(float $value): float {
    return $value * COMMISSION_RATE;
}

// Break-even market value: the value a position must reach so that selling nets
// exactly the cash paid in — after the 1% commission on BOTH legs AND the 10%
// capital-gains tax on the gross gain.
//   V·(1 − r − t) = B·(1 + r − t)  →  V = B·(1 + r − t)/(1 − r − t)
function breakeven_value(float $buyValue): float {
    if ($buyValue <= 0) return 0.0;
    return $buyValue * (1 + COMMISSION_RATE - TAX_RATE) / (1 - COMMISSION_RATE - TAX_RATE);
}

// ─── Ratio thresholds (green / orange; above orange = red) ───────────────────
define('PER_GREEN',  20);   define('PER_ORANGE',  25);
define('PEG_GREEN',   1);   define('PEG_ORANGE',   2);
define('PR_GREEN',  1.5);   define('PR_ORANGE',  2.0);
define('PB_GREEN',  2.0);   define('PB_ORANGE',  3.0);

// ─── Date formatting ──────────────────────────────────────────────────────────
// Converts Appwrite ISO timestamps (2026-05-22T00:00:00.000+00:00) to dd/mm/yyyy
function fmt_date(?string $iso, string $fallback = '—'): string {
    if (!$iso) return $fallback;
    try {
        return (new DateTime($iso))->format('d/m/Y');
    } catch (Exception $e) {
        return $fallback;
    }
}

// Market timezone. Timestamps are stored UTC; every user-facing time must be
// rendered in Casablanca local time, otherwise a 15:45 snapshot reads as 14:45
// and looks like stale data.
define('MARKET_TZ', 'Africa/Casablanca');

// Same input, but with the time of day — used wherever a reader could mistake a
// recent snapshot for an out-of-date one.
function fmt_datetime(?string $iso, string $fallback = '—'): string {
    if (!$iso) return $fallback;
    try {
        return (new DateTime($iso))->setTimezone(new DateTimeZone(MARKET_TZ))
                                   ->format('d/m/Y H:i');
    } catch (Exception $e) {
        return $fallback;
    }
}

// Time only, market timezone — for compact per-row "last seen" cells.
function fmt_time(?string $iso, string $fallback = '—'): string {
    if (!$iso) return $fallback;
    try {
        return (new DateTime($iso))->setTimezone(new DateTimeZone(MARKET_TZ))
                                   ->format('H:i');
    } catch (Exception $e) {
        return $fallback;
    }
}

// ─── Company name resolution ──────────────────────────────────────────────────
// Stored company names are the Casablanca Bourse short labels, which are often
// not what a person types. Someone looking for Maroc Telecom types "Maroc
// Telecom" or "ITM"; the stored name is "IAM". An exact-match lookup returns
// "Entreprise introuvable" and the search feature reads as broken.
//
// Every alias below maps a normalised user input to a stored company name.
// Keys are matched after norm_name(), so accents, punctuation and spacing do
// not matter — "S.M Monétique" and "sm monetique" both land on "S2M".
const COMPANY_ALIASES = [
    'MAROCTELECOM'          => 'IAM',
    'ITISSALATALMAGHRIB'    => 'IAM',
    'ITISSALAT'             => 'IAM',
    'ITM'                   => 'IAM',
    'MANAGEM'               => 'MANAGEM',
    'HOLCIM'                => 'LAFARGEHOLCIM MAROC',
    'HOLCIMMAROC'           => 'LAFARGEHOLCIM MAROC',
    'LAFARGE'               => 'LAFARGEHOLCIM MAROC',
    'SODEP'                 => 'MARSA MAROC',
    'SODEPMARSAMAROC'       => 'MARSA MAROC',
    'DOUJAPROMADDOHA'       => 'ADDOHA',
    'DOUJA'                 => 'ADDOHA',
    'SMMONETIQUE'           => 'S2M',
    'SMONETIQUE'            => 'S2M',
    'ATTIJARI'              => 'ATTIJARIWAFA BANK',
    'ATTIJARIWAFA'          => 'ATTIJARIWAFA BANK',
    'BANQUECENTRALEPOPULAIRE' => 'BCP',
    'BANQUEPOPULAIRE'       => 'BCP',
    'BMCE'                  => 'BANK OF AFRICA',
    'BMCEBANK'              => 'BANK OF AFRICA',
    'TOTALENERGIES'         => 'TOTALENERGIES MARKETING MAROC',
    'TOTAL'                 => 'TOTALENERGIES MARKETING MAROC',
    'OULMES'                => 'EAUX MINERALES OULMES',
    'BRASSERIESDUMAROC'     => 'BOISSONS DU MAROC',
    'SOCIETEDESBOISSONSDUMAROC' => 'BOISSONS DU MAROC',
    'CTMLN'                 => 'CTM',
    'REALISATIONSMECANIQUES' => 'SRM',
    'RESIDENCESDARSAADA'    => 'DAR SAADA',
    'PROMOPHARMSA'          => 'PROMOPHARM',
    'CIMENTSDUMAROC'        => 'CIMENTS DU MAROC',
    'MINIERETOUISSIT'       => 'MINIERE TOUISSIT',
    'CMT'                   => 'MINIERE TOUISSIT',
];

// Casefold for comparison: uppercase, strip accents, drop everything that is not
// a letter or a digit. "Zellidja S.A" and "zellidja sa" both become ZELLIDJASA.
function norm_name(string $s): string {
    $s = trim($s);
    if ($s === '') return '';
    $translit = @iconv('UTF-8', 'ASCII//TRANSLIT', $s);
    if ($translit !== false) $s = $translit;
    $s = strtoupper($s);
    return preg_replace('/[^A-Z0-9]/', '', $s) ?? '';
}

/**
 * Resolve free-typed text to a stored company name.
 *
 * @param string $input     what the user typed
 * @param array  $names     every stored company name
 * @param array  $symbolTo  symbol => company name (from the `format` collection)
 * @return array{name: ?string, suggestions: string[]}
 *         `name` is set on an unambiguous hit; otherwise `suggestions` holds
 *         the near misses to offer as "did you mean".
 */
function resolve_company(string $input, array $names, array $symbolTo = []): array {
    // Drop a Bloomberg/Reuters-style ".MA" market suffix before normalising —
    // norm_name() removes the dot, and "ATWMA" would no longer be strippable
    // without also mangling real names that end in MA (AGMA, AFMA, BALIMA).
    $input  = preg_replace('/\.\s*ma$/i', '', trim($input));
    $needle = norm_name($input);
    if ($needle === '') return ['name' => null, 'suggestions' => []];

    // 1. Exact stored name, ignoring case/accents/punctuation.
    foreach ($names as $n) {
        if (norm_name($n) === $needle) return ['name' => $n, 'suggestions' => []];
    }

    // 2. Ticker symbol — "ATW", "atw.ma".
    foreach ($symbolTo as $symbol => $company) {
        if (norm_name($symbol) === $needle) return ['name' => $company, 'suggestions' => []];
    }

    // 3. Curated alias.
    if (isset(COMPANY_ALIASES[$needle])) {
        $target = COMPANY_ALIASES[$needle];
        foreach ($names as $n) {
            if (norm_name($n) === norm_name($target)) {
                return ['name' => $n, 'suggestions' => []];
            }
        }
    }

    // 4. Substring, either direction — "attijari" finds "ATTIJARIWAFA BANK",
    //    and "zellidja sa maroc" still finds "ZELLIDJA S.A".
    $hits = [];
    foreach ($names as $n) {
        $hay = norm_name($n);
        if ($hay !== '' && (str_contains($hay, $needle) || str_contains($needle, $hay))) {
            $hits[] = $n;
        }
    }
    // Also let an alias key match on substring, so "telecom" reaches IAM.
    foreach (COMPANY_ALIASES as $alias => $target) {
        if (str_contains($alias, $needle) || str_contains($needle, $alias)) {
            foreach ($names as $n) {
                if (norm_name($n) === norm_name($target)) $hits[] = $n;
            }
        }
    }
    $hits = array_values(array_unique($hits));

    if (count($hits) === 1) return ['name' => $hits[0], 'suggestions' => []];
    if (count($hits) > 1)   return ['name' => null, 'suggestions' => $hits];

    // 5. Nothing matched — offer the closest names so the page is never a
    //    dead end. Levenshtein over ~80 short strings is free.
    $scored = [];
    foreach ($names as $n) {
        $scored[$n] = levenshtein($needle, norm_name($n));
    }
    asort($scored);
    $close = array_slice(array_keys($scored), 0, 5);
    $close = array_values(array_filter($close, fn($n) => $scored[$n] <= max(4, strlen($needle) / 2)));

    return ['name' => null, 'suggestions' => $close];
}

// ─── CSRF helpers ─────────────────────────────────────────────────────────────
function csrf_token(): string {
    if (session_status() === PHP_SESSION_NONE) session_start();
    if (empty($_SESSION['csrf_token'])) {
        $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
    }
    return $_SESSION['csrf_token'];
}

function csrf_verify(): void {
    $token = $_POST['csrf_token'] ?? '';
    if (!hash_equals($_SESSION['csrf_token'] ?? '', $token)) {
        http_response_code(403);
        die('Invalid request (CSRF token mismatch).');
    }
}

function csrf_field(): string {
    return '<input type="hidden" name="csrf_token" value="'
        . htmlspecialchars(csrf_token(), ENT_QUOTES) . '">';
}
