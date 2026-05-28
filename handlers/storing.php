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
function store(Company $company): string {
    $fundamentals = [];
    if ($company->BPA) $fundamentals['bpa'] = (float)$company->BPA;
    if ($company->DPA) $fundamentals['dpa'] = (float)$company->DPA;
    if ($company->TC5) $fundamentals['tc5'] = (float)$company->TC5;
    if ($company->ROE) $fundamentals['roe'] = (float)$company->ROE;
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
