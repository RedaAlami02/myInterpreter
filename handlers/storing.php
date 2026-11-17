<?php
require_once __DIR__ . '/../core/Appwrite.php';
require_once __DIR__ . '/../core/Action.php';

/**
 * Persist an administrator analysis.
 * - Updates fundamental fields on the company record (exact name).
 * - Inserts an explicit operator-entered snapshot into the app history.
 *
 * @return array{name:string,fields:int,snapshot:bool}
 * @throws RuntimeException on a rejected or unavailable write.
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

function store(Company $company): array {
    $fundamentals = [];
    if ($company->BPA || in_array('BPA', $company->providedFields, true)) $fundamentals['bpa'] = (float)$company->BPA;
    if ($company->DPA || in_array('DPA', $company->providedFields, true)) $fundamentals['dpa'] = (float)$company->DPA;
    if ($company->TC5 || in_array('TC5', $company->providedFields, true)) {
        assert_percent_unit('TC5', (float)$company->TC5);
        $fundamentals['tc5'] = (float)$company->TC5;
    }
    if ($company->ROE || in_array('ROE', $company->providedFields, true)) {
        assert_percent_unit('ROE', (float)$company->ROE);
        $fundamentals['roe'] = (float)$company->ROE;
    }
    if ($company->NA || in_array('NA', $company->providedFields, true))  $fundamentals['na']  = (float)$company->NA;
    if ($company->CP || in_array('CP', $company->providedFields, true))  $fundamentals['cp']  = (float)$company->CP;

    $saved = 0;
    if (!empty($fundamentals)) {
        try {
            $receipt = sb_admin()->updateCompany(
                sb_access_token(), $company->NAME, $fundamentals
            );
        } catch (SupabaseRequestException $e) {
            error_log('[myInterpreter] store() company denied or unavailable for "' . $company->NAME . '": ' . $e->httpStatus);
            throw new RuntimeException('Impossible de sauvegarder la fiche société.');
        } catch (Throwable $e) {
            error_log('[myInterpreter] store() company error for "' . $company->NAME . '": ' . $e->getMessage());
            throw new RuntimeException('Impossible de sauvegarder la fiche société.');
        }
        if ($receipt['status'] === 'MISSING') {
            throw new RuntimeException(
                'Société introuvable : la fiche société doit exister avant l\'enregistrement.'
            );
        }
        $saved = (int)($receipt['fields'] ?? 0);
    }

    // A zero or missing price is not a market observation and never becomes history.
    $snapshot = null;
    if ((float)$company->PA > 0) {
        $snapshot = array_filter([
            'c_name' => $company->NAME,
            'pa'     => (float)$company->PA,
            'cb'     => $company->CB ? (float)$company->CB : null,
            'per'    => $company->PER ? (float)$company->PER : null,
            'peg'    => $company->PEG ? (float)$company->PEG : null,
            'pr'     => $company->PR ? (float)$company->PR : null,
            'pb'     => $company->PB ? (float)$company->PB : null,
        ], fn($v) => $v !== null && $v !== '');
        try {
            sb_admin()->recordOperatorSnapshot(sb_access_token(), $snapshot);
        } catch (SupabaseRequestException $e) {
            error_log('[myInterpreter] store() snapshot denied or unavailable for "' . $company->NAME . '": ' . $e->httpStatus);
            throw new RuntimeException('Impossible de sauvegarder le snapshot.');
        } catch (Throwable $e) {
            error_log('[myInterpreter] store() snapshot error for "' . $company->NAME . '": ' . $e->getMessage());
            throw new RuntimeException('Impossible de sauvegarder le snapshot.');
        }
    }

    return ['name' => $company->NAME, 'fields' => $saved, 'snapshot' => $snapshot !== null];
}
