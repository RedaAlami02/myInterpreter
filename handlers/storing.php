<?php
require_once __DIR__ . '/../core/Appwrite.php';
require_once __DIR__ . '/../core/Action.php';

/**
 * Persist a Company to Appwrite.
 * - UPSERT into company collection (fundamental data)
 * - INSERT snapshot into data collection (price + ratios)
 *
 * @return string  The company name saved.
 * @throws RuntimeException on Appwrite failure (details in error_log)
 */
/**
 * TC5 and ROE are stored as percentages ("22.51" means 22.51 %). The manual
 * Update form accepts whatever is typed, and rows entered as fractions ("0.28"
 * meaning 28 %) reached production — where PEG = PER / 0.28 produced values
 * like 97.57 that read as real ratios. There is no way to distinguish a
 * fraction from a genuinely tiny percentage from the value alone, so reject the
 * ambiguous range and make the operator state the unit explicitly.
 */
function assert_percent_unit(string $label, float $val): void {
    if ($val != 0.0 && abs($val) < 1.0) {
        throw new RuntimeException(
            "$label = $val est ambigu : saisissez un pourcentage (ex. 28.4 pour 28,4 %), " .
            "pas une fraction (0.284). Pour une valeur réellement inférieure à 1 %, saisissez 0."
        );
    }
}

function store(Company $company): string {
    $fundamentals = [];
    if ($company->BPA) $fundamentals['bpa'] = (float)$company->BPA;
    if ($company->DPA) $fundamentals['dpa'] = (float)$company->DPA;
    if ($company->TC5) {
        assert_percent_unit('TC5', (float)$company->TC5);
        $fundamentals['tc5'] = (float)$company->TC5;
    }
    if ($company->ROE) {
        assert_percent_unit('ROE', (float)$company->ROE);
        $fundamentals['roe'] = (float)$company->ROE;
    }
    if ($company->NA)  $fundamentals['na']  = (float)$company->NA;
    if ($company->CP)  $fundamentals['cp']  = (float)$company->CP;

    try {
        if ($company->stored && !empty($company->_awId)) {
            if (!empty($fundamentals)) {
                aw_update_doc('company', $company->_awId, $fundamentals);
            }
        } else {
            $existing = aw_list_docs('company', [q_equal('name', $company->NAME), q_limit(1)]);
            if (!empty($existing)) {
                if (!empty($fundamentals)) {
                    aw_update_doc('company', $existing[0]['$id'], $fundamentals);
                }
            } else {
                $fundamentals['name'] = $company->NAME;
                $fundamentals['date'] = gmdate('Y-m-d\TH:i:s.000+00:00');
                aw_create_doc('company', $fundamentals);
            }
        }
    } catch (Throwable $e) {
        error_log('[myInterpreter] store() company error for "' . $company->NAME . '": ' . $e->getMessage());
        throw new RuntimeException('Impossible de sauvegarder la fiche société.');
    }

    try {
        aw_create_doc('data', [
            'date'   => gmdate('Y-m-d\TH:i:s.000+00:00'),
            'pa'     => (float)$company->PA,
            'cb'     => (float)$company->CB,
            'per'    => (float)$company->PER,
            'peg'    => (float)$company->PEG,
            'pr'     => (float)$company->PR,
            'pb'     => (float)$company->PB,
            'c_name' => $company->NAME,
        ]);
    } catch (Throwable $e) {
        error_log('[myInterpreter] store() data snapshot error for "' . $company->NAME . '": ' . $e->getMessage());
        throw new RuntimeException('Impossible de sauvegarder le snapshot.');
    }

    return $company->NAME;
}
