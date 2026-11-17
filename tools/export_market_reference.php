<?php
// Pure public reference data and reviewed issuer filings; no configuration/keys.
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require_once __DIR__ . '/../core/sector_allocation.php';
require_once __DIR__ . '/../core/company_disclosures.php';
$input = json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
$profiles = [];
foreach ($input['profiles'] ?? [] as $profile) {
    $reviewed = apply_reviewed_disclosure($profile['symbol'],$profile);
    foreach (['computed','charts','description','sector','shareholders','interim'] as $field) {
        if (($reviewed[$field] ?? null) !== ($profile[$field] ?? null)) {
            $reviewed['field_origins'][$field] = 'reviewed_public_filing';
        }
    }
    $profiles[] = $reviewed;
}
echo json_encode([
    'reference'=>['sector_publication_date'=>MARKET_SECTOR_DATE,'sectors'=>MARKET_SECTORS,
        'issuer_classifications'=>MARKET_ISSUERS,'reviewed_disclosures'=>['T2S'=>reviewed_company_disclosure('T2S')]],
    'profiles'=>$profiles,
],JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
