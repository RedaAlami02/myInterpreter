<?php
require_once __DIR__ . '/../core/Database.php';
require_once __DIR__ . '/../core/Action.php';

/**
 * Persist a Company to the database.
 * - UPSERT into company (fundamental data)
 * - INSERT snapshot into DATA (price + ratios)
 *
 * @return string  The company name saved.
 */
function store(Company $company): string {
    $db = (new Database())->opendb();

    if ($company->stored) {
        $db->prepare(
            'UPDATE company SET BPA=?, TC5=?, ROE=?, NA=?, CP=? WHERE NAME=?'
        )->execute([
            $company->BPA, $company->TC5, $company->ROE,
            $company->NA,  $company->CP,  $company->NAME,
        ]);
    } else {
        $db->prepare(
            'INSERT INTO company (NAME, BPA, TC5, ROE, NA, CP, `DATE`)
             VALUES (?, ?, ?, ?, ?, ?, CURRENT_DATE)'
        )->execute([
            $company->NAME, $company->BPA, $company->TC5,
            $company->ROE,  $company->NA,  $company->CP,
        ]);
    }

    $db->prepare(
        'INSERT INTO `data` (`DATE`, PA, CB, PER, PEG, PR, PB, C_NAME)
         VALUES (SYSDATE(), ?, ?, ?, ?, ?, ?, ?)'
    )->execute([
        $company->PA, $company->CB,  $company->PER,
        $company->PEG, $company->PR, $company->PB, $company->NAME,
    ]);

    return $company->NAME;
}
