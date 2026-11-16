<?php
// Bourse de Casablanca, Bulletin de la cote, séance du 28/09/2026.
// T2S healthcare classification supplemented from its exchange instrument record.
// One listed issuer per line. Refresh this snapshot when the listing changes.
const MARKET_SECTOR_DATE = '28/09/2026';
const MARKET_SECTORS = [
    'AGR' => 'Agroalimentaire et Production',
    'ASS' => 'Assurances',
    'BAN' => 'Banques',
    'BMC' => 'Bâtiment et Matériaux de Construction',
    'BOI' => 'Boissons',
    'CHI' => 'Chimie',
    'DIS' => 'Distributeurs',
    'ELC' => 'Électricité',
    'IAG' => 'Industrie Agricole',
    'IBE' => "Ingénieries et Biens d'Équipement Industriels",
    'IMM' => 'Participation et promotion immobilières',
    'LH'  => 'Loisirs et Hôtels',
    'LSI' => 'Matériels, Logiciels et Services Informatiques',
    'MIN' => 'Mines',
    'PEG' => 'Pétrole et Gaz',
    'PHA' => 'Industrie Pharmaceutique',
    'SAN' => 'Santé',
    'SDT' => 'Services de transport',
    'SFA' => 'Sociétés de financement et Autres Activités Financières',
    'SP'  => 'Sylviculture et Papier',
    'SPH' => 'Sociétés de Portefeuilles / Holdings',
    'SPI' => 'Sociétés de placement immobilier',
    'TCO' => 'Télécommunications',
    'TRP' => 'Transport',
];

const MARKET_ISSUERS = <<<'ISSUERS'
AFRIQUIA GAZ|PEG
AKDITAL|SAN
ALLIANCES|IMM
ATLANTASANAD|ASS
ATTIJARIWAFA BANK|BAN
BANK OF AFRICA|BAN
BCP|BAN
BMCI|BAN
CDM|BAN
CIMENTS DU MAROC|BMC
CMGP GROUP|IAG
COSUMAR|AGR
CIH|BAN
DELTA HOLDING|SPH
DOUJA PROM ADDOHA|IMM
Holcim Maroc S.A|BMC
ITISSALAT AL-MAGHRIB|TCO
JET CONTRACTORS|BMC
LABEL VIE|DIS
LESIEUR CRISTAL|AGR
MANAGEM|MIN
RISMA|LH
SANLAM MAROC|ASS
SOCIETE DES BOISSONS DU MAROC|BOI
SOTHEMA|PHA
SODEP-Marsa Maroc|SDT
SGTM S.A|BMC
SONASID|BMC
TAQA MOROCCO|ELC
TOTALENERGIES MARKETING MAROC|PEG
WAFA ASSURANCE|ASS
AFMA|ASS
AFRIC INDUSTRIES SA|BMC
ALUMINIUM DU MAROC|BMC
AUTO HALL|DIS
AUTO NEJMA|DIS
BALIMA|SPI
CARTIER SAADA|AGR
CTM|TRP
MINIERE TOUISSIT|MIN
DARI COUSPATE|AGR
DELATTRE LEVIVIER MAROC|IBE
DISWAY|LSI
ENNAKL|DIS
EQDOM|SFA
FENIE BROSSETTE|DIS
HPS|LSI
IB MAROC.COM|LSI
IMMORENTE INVEST|SPI
M2M Group|LSI
MAGHREBAIL|SFA
MAGHREB OXYGENE|CHI
MAROC LEASING|SFA
MUTANDIS SCA|AGR
REBAB COMPANY|MIN
RESIDENCES DAR SAADA|IMM
SALAFIN|SFA
SAMIR|PEG
PROMOPHARM S.A.|PHA
REALISATIONS MECANIQUES|DIS
OULMES|BOI
S.M MONETIQUE|LSI
SMI|MIN
SNEP|CHI
STOKVIS NORD AFRIQUE|DIS
STROC INDUSTRIE|IBE
UNIMER|AGR
ZELLIDJA S.A|SPH
ARADEI CAPITAL|SPI
CASH PLUS S.A|SFA
CFG BANK|BAN
TGCC S.A|BMC
VICENNE|SAN
T2S Group Holding|SAN
AGMA|ASS
COLORADO|BMC
DISTY TECHNOLOGIES|LSI
INVOLYS|LSI
MICRODATA|LSI
ISSUERS;

// Portfolio/company naming differs from the official bulletin for these issuers.
const MARKET_NAME_ALIASES = [
    'ADDOHA' => 'DOUJA PROM ADDOHA',
    'AFRIC INDUSTRIES' => 'AFRIC INDUSTRIES SA',
    'BOISSONS DU MAROC' => 'SOCIETE DES BOISSONS DU MAROC',
    'CASH PLUS' => 'CASH PLUS S.A',
    'CIH BANK' => 'CIH',
    'CREDIT DU MAROC' => 'CDM',
    'DAR SAADA' => 'RESIDENCES DAR SAADA',
    'EAUX MINERALES OULMES' => 'OULMES',
    'IAM' => 'ITISSALAT AL-MAGHRIB',
    'LAFARGEHOLCIM MAROC' => 'Holcim Maroc S.A',
    'MARSA MAROC' => 'SODEP-Marsa Maroc',
    'MUTANDIS' => 'MUTANDIS SCA',
    'PROMOPHARM' => 'PROMOPHARM S.A.',
    'S2M' => 'S.M MONETIQUE',
    'SGTM' => 'SGTM S.A',
    'SRM' => 'REALISATIONS MECANIQUES',
    'TGCC' => 'TGCC S.A',
];

function market_issuer_sectors(): array
{
    static $issuerSectors = null;
    if ($issuerSectors === null) {
        $issuerSectors = [];
        foreach (explode("\n", MARKET_ISSUERS) as $line) {
            [$issuer, $sector] = explode('|', trim($line), 2);
            $issuerSectors[$issuer] = $sector;
        }
    }
    return $issuerSectors;
}

function market_sector_for_company(string $name): ?string
{
    $issuer = MARKET_NAME_ALIASES[$name] ?? $name;
    return market_issuer_sectors()[$issuer] ?? null;
}

function market_sector_directory(array $companyNames): array
{
    $directory = array_fill_keys(array_keys(MARKET_SECTORS), []);
    $directory['OTHER'] = [];
    foreach (array_unique($companyNames) as $name) {
        $code = market_sector_for_company($name) ?? 'OTHER';
        $directory[$code][] = $name;
    }
    foreach ($directory as &$names) sort($names, SORT_NATURAL | SORT_FLAG_CASE);
    unset($names);
    return $directory;
}

function market_sector_allocation(array $holdings): array
{
    $issuerSectors = market_issuer_sectors();
    $marketCounts = array_fill_keys(array_keys(MARKET_SECTORS), 0);
    foreach ($issuerSectors as $sector) {
        $marketCounts[$sector]++;
    }

    $heldCounts = array_fill_keys(array_keys(MARKET_SECTORS), 0);
    $sectorValues = array_fill_keys(array_keys(MARKET_SECTORS), 0.0);
    $heldCompanies = array_fill_keys(array_keys(MARKET_SECTORS), []);
    $heldCompanies['OTHER'] = [];
    $unclassified = [];
    $unclassifiedValue = 0.0;
    $seen = [];
    foreach ($holdings as $holding) {
        $name = trim((string)($holding['c_name'] ?? ''));
        if ($name === '' || (float)($holding['quantity'] ?? 0) <= 0) continue;
        $issuer = MARKET_NAME_ALIASES[$name] ?? $name;
        $sector = $issuerSectors[$issuer] ?? null;
        $value = max(0, (float)($holding['current_value'] ?? 0));
        if ($sector === null) {
            $unclassifiedValue += $value;
            if (!isset($seen[$issuer])) $unclassified[] = $name;
        } else {
            $sectorValues[$sector] += $value;
            if (!isset($seen[$issuer])) $heldCounts[$sector]++;
        }
        $key = $sector ?? 'OTHER';
        if (!isset($heldCompanies[$key][$issuer])) {
            $heldCompanies[$key][$issuer] = ['name' => $name, 'value' => 0.0, 'has_price' => false];
        }
        $heldCompanies[$key][$issuer]['value'] += $value;
        $heldCompanies[$key][$issuer]['has_price'] = $heldCompanies[$key][$issuer]['has_price'] || (bool)($holding['has_price'] ?? $value > 0);
        $seen[$issuer] = true;
    }

    $rows = [];
    foreach (MARKET_SECTORS as $code => $label) {
        if ($marketCounts[$code] === 0) continue;
        $rows[] = ['code' => $code, 'label' => $label, 'held' => $heldCounts[$code], 'market' => $marketCounts[$code], 'value' => $sectorValues[$code]];
    }
    usort($rows, fn($a, $b) => ($b['held'] <=> $a['held']) ?: strcmp($a['label'], $b['label']));
    foreach ($heldCompanies as &$companies) $companies = array_values($companies);
    unset($companies);
    return ['rows' => $rows, 'unclassified' => $unclassified,
        'unclassified_value' => $unclassifiedValue, 'held_companies' => $heldCompanies];
}
