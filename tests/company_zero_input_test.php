<?php
require_once __DIR__ . '/../core/Action.php';
$company = new Company(['NAME' => 'Example', 'BPA' => '0', 'DPA' => '', 'ROE' => '-2']);
if ($company->BPA !== 0.0 || !in_array('BPA', $company->providedFields, true)
    || in_array('DPA', $company->providedFields, true) || $company->ROE !== -2.0) {
    throw new RuntimeException('Explicit zero and blank inputs must remain distinct.');
}
echo "Company zero input regression passed.\n";

$company = new Company(['PA' => 100, 'BPA' => 10, 'TC5' => 5,
    'ROE' => 20, 'NA' => 10, 'CP' => 500]);
$company->calcul();
if ($company->PER !== 10.0 || $company->PB !== 2.0) {
    throw new RuntimeException('Initial ratios are incorrect.');
}
$company->BPA = $company->TC5 = $company->ROE = $company->CP = 0.0;
$company->calcul();
foreach (['PER', 'PEG', 'PR', 'PB'] as $ratio) {
    if ($company->$ratio !== 0.0) throw new RuntimeException('Stale ratio: ' . $ratio);
}
echo "Repeated calculation regression passed.\n";
