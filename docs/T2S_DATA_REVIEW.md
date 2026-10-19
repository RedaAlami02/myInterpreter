# T2S data review — 19 October 2026

The existing company record used 2024 accounts, treated 2025 earnings as a
forecast, and lacked a profile and healthcare classification. Its price was
current. The annual chart also mixed 2024 net income with 2025 revenue/equity.

## Public evidence (not runtime data-provider configuration)

- [2025 reference document](https://www.ammc.ma/sites/default/files/T2S_IPO_DR_010_2026_2.pdf): printed pp. 211, 219, 221, 239, 241.
  Annual revenue 1,763.333 MMAD; group net income 204.576 MMAD; group equity
  1,410.404 MMAD; total assets 3,271.222 MMAD; operating profit 381.212 MMAD.
  Figures are converted from KMAD to MMAD, or MAD for stored equity.
- EBE uses the explicitly identified EBE in the debt-ratio table (p.239):
  245.850 / 275.748 / 388.402 MMAD for 2023/2024/2025, not operating profit
  before provisions including non-recurring items (453.680 MMAD in 2025).
- Net debt is 222.346 MMAD using the issuer's definition. Net cash here is
  cash assets less cash liabilities: 359.641 − 156.820 = 202.821 MMAD.
  FCF follows the site's operating-plus-investing-cash-flow convention:
  318.466 − 26.165 = 292.301 MMAD (not operating cash flow less gross capex).
- [Current exchange share listing](https://www.casablanca-bourse.com/ar/marches-produits/actions):
  22,584,118 shares after the October capital increase, replacing 21,785,174.
  [Instrument classification](https://www.casablanca-bourse.com/fr/live-market/instruments/T2S): healthcare.
- [Issuer record](https://www.ammc.ma/fr/espace-emetteurs/liste-des-emetteurs/55122):
  July 27 shareholder distribution. It is displayed as a dated historical
  snapshot, explicitly before the October increase, not as current ownership.
- [H1 2026 release](https://www.ammc.ma/sites/default/files/CP_T2S_group_S1_26.pdf):
  revenue 978, EBE 243, reported group net income 91 MMAD; H1 2025 comparatives
  773, 170, 109. The adjusted 55 MMAD comparator is NOT substituted for reported
  earnings. Interim figures are shown separately and not annualized.

## Application and safeguards

`core/company_disclosures.php` supplies reviewed historical chart corrections
and a fallback if the normal enrichment is unavailable. Newer reported annual
earnings remain eligible to replace the current computed values. The older
2025 forecast is removed once its actual result is present; future projections
remain projections. No invented dividend, beta or five-year growth is added.

`tools/apply_reviewed_company.php T2S` previews the single-company database patch;
`--apply` backs up the public company record outside the website and verifies the
write. It never changes permissions, prices or historical price snapshots.
EPS is normalized using current shares (9.06 MAD), not the historical weighted
average share count. ROE follows the site's closing group-equity convention
(14.50%), not the issuer's average-total-equity ROE (15.8%).

The existing price job should pick up revised fundamentals on its next run.
Historical ratios are deliberately not rewritten. No cloud function was
redeployed; unknown five-year growth and beta remain blank. Review the supplement
when newer accounts, share counts or shareholder disclosures appear.
