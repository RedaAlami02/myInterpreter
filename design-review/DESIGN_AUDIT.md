# Interface Design Audit

Observed 2 September 2026 at commit `a323dca` on the local PHP server. Public market data rendered from the configured backend; no records were written. Portfolio findings are source-only because no authorized clean demo account was available. Flutter was inspected from source; `adb devices -l` found no connected device.

## Evidence Index

| Screen | Route / state | Viewport | Evidence |
|---|---|---:|---|
| Screener | `/screener.php`, public live data | 1440×1100 | [`screenshots/before/screener-desktop.png`](screenshots/before/screener-desktop.png) |
| Screener | same data, narrow layout | 390×844 | [`screenshots/before/screener-mobile.png`](screenshots/before/screener-mobile.png) |
| Company detail | `/infoAction.php?name=MAROC%20TELECOM`, public live data | 1440×1100 | [`screenshots/before/company-desktop.png`](screenshots/before/company-desktop.png) |
| Dashboard | `/index.php`, signed out | 1440×1000 | [`screenshots/before/dashboard-logged-out.png`](screenshots/before/dashboard-logged-out.png) |
| Dividends | `/dividendes.php`, public live data | 1440×1000 | [`screenshots/before/dividends-desktop.png`](screenshots/before/dividends-desktop.png) |

“Live data” here means actual configured backend reads, not a claim that exchange prices are real-time; the UI itself states that prices are delayed.

## Overall Assessment

The interface is functional and already has deliberate styling, but it reads as a collection of dashboard patterns more than one authored financial workspace. The generic impression comes from the combination of neon cyan/purple halos, glass panels, many rounded cards, small uppercase labels, three typefaces, and an icon on nearly every heading. These devices compete with the numbers instead of establishing task order. The strongest assets are the dense real data, consistent numeric typeface, useful semantic signs, and compact navigation.

The recommended redesign should preserve density and the dark option, but make surfaces flatter, labels clearer, and comparison structures more deliberate. A warm, editorial “ledger” direction is also worth testing because it would give the project a more distinctive Casablanca research identity without changing product behavior.

## Findings

| ID | Screen / component | Evidence and status | User impact | Priority | Proposed change | Behavior risk |
|---|---|---|---|---|---|---|
| DESIGN-01 | Shared visual system | `global.css:8-50` and `:465-493` define two overlapping token sets; runtime screens use both generations. **SOURCE + RUNTIME** | Similar cards, text, and accents vary subtly across pages; maintenance encourages more one-off styles. | High | Consolidate the pilot around one surface/text/accent scale, then migrate shared components incrementally. | Token changes can affect every page; scope pilot overrides first. |
| DESIGN-02 | Screener metrics | Five metrics use a four-column grid; the fifth sits alone on a second row. Desktop screenshot. **RUNTIME** | Wastes vertical space and makes “without PER” look detached from the market summary. | High | Use one primary result metric and a compact secondary metric strip, or a balanced five-column band. | None if values and IDs remain unchanged. |
| DESIGN-03 | Screener mobile | At 390 px, intrinsic grid/filter widths extend beyond the viewport; cards and controls are clipped by `body { overflow-x:hidden }`. Mobile screenshot. **RUNTIME** | Information becomes unreachable rather than intentionally scrollable. | Critical | Set `min-width:0`, use a single-column summary, wrap controls within the viewport, and contain table overflow with a visible cue/sticky identity column. | Must preserve filter and sorting hooks. |
| DESIGN-04 | Mobile navigation | Sidebar becomes a horizontally scrolling row with no menu affordance; later destinations and active state can start off-screen. Mobile screenshot and `global.css:783-801`. **RUNTIME + SOURCE** | Navigation is discoverable only by swiping an unlabeled strip. | High | Use a compact top bar plus explicit scroll cue or a menu/drawer in the shared rollout. | Shared navigation and auth actions need regression checks. |
| DESIGN-05 | Typography / contrast | Muted labels use `#475569`, commonly at 10–12 px, over very dark surfaces; runtime freshness, headings, and headers are visibly faint. **RUNTIME + SOURCE** | Important context (date, units, definitions) is harder to read; hierarchy relies on low opacity. | High | Raise secondary-text contrast, reserve uppercase tracking for section labels, and keep body copy at readable sizes. | Visual only. |
| DESIGN-06 | Visual noise | Ambient radial halos, blur/glass, glow shadows, gradient actions, badge borders, and repeated icons appear together (`global.css`, all screenshots). **RUNTIME + SOURCE** | Decoration fragments attention and produces the “AI dashboard” feel despite good data. | Medium | Prefer opaque neutral surfaces, hairline separators, one accent, and icons only where they add recognition. | Removing blur must not alter stacking contexts. |
| DESIGN-07 | Screener language and terms | “Stock Screener” and English abbreviations sit inside otherwise French navigation/content; ratio explanations exist only in hover `title`s. **RUNTIME** | Terminology feels unfinished; touch and keyboard users cannot rely on hover help. | Medium | Rename the page “Sélection d’actions”; add a visible compact ratio key and accessible abbreviations. | Do not change calculation meanings or column indexes. |
| DESIGN-08 | Sort controls | Click handlers live on `<th>` elements with no keyboard button or `aria-sort` (`screener.php:246-275`). **SOURCE** | Sorting is not operable or announced consistently for keyboard/assistive-tech users. | High | Put real buttons in headers, retain column indexes, update `aria-sort` in existing JS. | Sorting JS is a core pilot regression risk. |
| DESIGN-09 | Touch controls | Preset buttons are roughly 27 px tall (`screener.css:51-60`). **SOURCE + MOBILE RUNTIME** | Targets are cramped and difficult to operate on a phone. | High | Make narrow-screen controls at least 40–44 px high and keep selected state textual. | Filter behavior must remain unchanged. |
| DESIGN-10 | Company detail hierarchy | Search dominates even after a company is selected; nine KPI cards have equal emphasis and wrap with “Marge” alone. Company screenshot. **RUNTIME** | The current quote, change, and key fundamentals do not establish a clear first reading path. | Medium | Convert search to a compact utility row and group quote, valuation, profitability, and scale metrics. | Preserve search and chart range hooks. |
| DESIGN-11 | Chart context | Company chart has period controls and axes, but the prominent red line reads as “loss” regardless of selected period or actual movement; unit/date context is faint. **RUNTIME** | Color may imply a negative state the chart has not explicitly established. | Medium | Use a neutral/accent line by default, explicit MAD axis/unit, start/end/change summary, and clearer selected period. | Chart data and slider interactions must remain unchanged. |
| DESIGN-12 | Dividends scan path | Guidance, counts, year tabs, and schedule all use separate rounded containers; long explanatory text has low contrast. Dividend screenshot. **RUNTIME** | Users scan through chrome before reaching upcoming payments. | Medium | Lead with the next payment window and concise totals; move methodology into a quieter disclosure. | Date-type/status meanings must remain unchanged. |
| DESIGN-13 | Portfolio / transactions | Three summary cards, two allocation doughnuts, holdings, dividend panel, snapshot action, transaction forms, and FIFO history share one tabbed page (`portfolio.php:297-617`). **SOURCE-ONLY** | Likely long and cognitively mixed; frequent “check holdings” tasks compete with maintenance and accounting actions. | High | Group overview/holdings first; make transactions a purposeful action flow; label fee/break-even estimates explicitly. | Protected data and known calculation defects prohibit fixture claims or silent logic fixes. |
| DESIGN-14 | Financial labels | Holdings columns say “Frais” and “Seuil équilibre” while calculations represent configured estimates (`portfolio.php:393-425`). **SOURCE-ONLY** | Labels can sound authoritative and obscure assumptions. | High | Use “Frais de transaction estimés” and “Équilibre estimé après frais et impôt,” with configuration note. | Copy only; correctness issues remain separately blocked. |
| DESIGN-15 | Feedback states | PHP has alerts/loading overlay; public screens show empty/error copy, but stale-data treatment is mostly a faint timestamp. Flutter has loading/error/retry states in source. **SOURCE + PARTIAL RUNTIME** | A delayed or preserved price is easy to mistake for current market activity. | High | Make freshness/status a readable status line and preserve “non traité” as text, not color alone. | Must not fabricate freshness or source status. |
| DESIGN-16 | Flutter identity | Flutter uses a GitHub-like charcoal/gold theme while web uses cyan/violet glass (`main.dart:8-150`). **SOURCE-ONLY** | Web and mobile do not yet feel like the same product. | Medium | After web direction is confirmed, translate the same neutral/accent/semantic roles into Material components. | No device is available for visual validation; defer implementation. |
| DESIGN-17 | Flutter list density | Screener and statistics repeat one rounded card per row (`screener.dart:177-243`, statistics source). **SOURCE-ONLY** | Comparison is weaker than a structured compact list, and vertical scrolling increases. | Medium | Use grouped list rows with aligned value columns and fewer enclosing cards. | Must test on a real/emulated device later. |

## Representative Pilot

The public screener is the safest representative screen: it uses real numerical content, dense comparisons, filters, sorting, freshness, semantic states, and a difficult mobile layout. The portfolio would be more central, but it cannot be visually audited without safe authorized data. The screener pilot must therefore prove the shared hierarchy and responsive rules without being treated as evidence for portfolio calculations.

## Pilot Outcome

The Atlas Ledger pilot resolves `DESIGN-02`, `DESIGN-03`, `DESIGN-07`, `DESIGN-08`, and `DESIGN-09` on the screener. It also demonstrates a scoped treatment for `DESIGN-01`, `DESIGN-05`, `DESIGN-06`, and `DESIGN-15`; those shared findings remain open elsewhere. Mobile navigation (`DESIGN-04`) is resolved on the pilot route through a five-item fitted bar and concise shared labels, but other routes still use the older responsive styling. See [`DESIGN_SPEC.md`](DESIGN_SPEC.md) and [`VALIDATION.md`](VALIDATION.md) before extending the work.

## Constraints and Open Evidence

- No protected portfolio screenshots or private records were captured.
- No local fixture was needed for the public-screen pilot.
- No Android device/emulator was connected, so Flutter visuals remain source hypotheses.
- Hover, keyboard sorting, filter interaction, and narrow-screen overflow require explicit validation after the pilot.
- Live counts and timestamps can change between before/after captures; compare structure and stable row values, noting expected data updates.
