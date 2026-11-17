<?php
require_once __DIR__ . '/../config/config.php';

class Company {
    // Traffic-light labels
    const RESULT = ['green', 'orange', 'red'];

    public string $NAME  = '';
    public bool   $stored = false;
    public array $providedFields = [];

    // Raw inputs
    public float $PA  = 0.0;
    public float $BPA = 0.0;
    public float $DPA = 0.0;
    public float $TC5 = 0.0;
    public float $ROE = 0.0;
    public float $NA  = 0.0;
    public float $CP  = 0.0;

    // Calculated
    public float $CB  = 0.0;   // Market cap
    public float $PER = 0.0;
    public float $PEG = 0.0;
    public float $PR  = 0.0;   // P/ROE
    public float $PB  = 0.0;   // Price-to-book

    public function __construct(array $data = []) {
        $this->providedFields = array_keys(array_filter($data,
            fn($value) => $value !== '' && $value !== null));
        $this->NAME = (string) ($data['NAME'] ?? '');
        $this->PA   = (float) ($data['PA']   ?? 0.0);
        $this->BPA  = (float) ($data['BPA']  ?? 0.0);
        $this->DPA  = (float) ($data['DPA']  ?? 0.0);
        $this->TC5  = (float) ($data['TC5']  ?? 0.0);
        $this->ROE  = (float) ($data['ROE']  ?? 0.0);
        $this->NA   = (float) ($data['NA']   ?? 0.0);
        $this->CP   = (float) ($data['CP']   ?? 0.0);
    }

    public function calcul(): void {
        // Recalculation must not retain ratios whose denominator is now zero.
        $this->PER = $this->PEG = $this->PR = $this->PB = 0.0;
        $this->CB = $this->PA * $this->NA;

        if ($this->BPA != 0) {
            $this->PER = $this->PA / $this->BPA;
        }
        if ($this->TC5 != 0 && $this->PER != 0) {
            $this->PEG = $this->PER / $this->TC5;
        }
        if ($this->ROE != 0 && $this->PER != 0) {
            $this->PR = $this->PER / $this->ROE;
        }
        if ($this->CP != 0 && $this->CB != 0) {
            $this->PB = $this->CB / $this->CP;
        }
    }

    /**
     * Returns a color label for each ratio based on config thresholds.
     * @return array<string,string>
     */
    public function test(): array {
        $r = self::RESULT;
        // A zero or negative ratio is missing or loss-making information, not a
        // cheap company. Scoring it against the thresholds badged it green.
        $score = static function (float $value, float $green, float $orange) use ($r): string {
            if ($value <= 0) return 'none';
            return $value < $green ? $r[0] : ($value < $orange ? $r[1] : $r[2]);
        };
        return [
            'PER' => $score($this->PER, PER_GREEN, PER_ORANGE),
            'PEG' => $score($this->PEG, PEG_GREEN, PEG_ORANGE),
            'PR'  => $score($this->PR, PR_GREEN, PR_ORANGE),
            'PB'  => $score($this->PB, PB_GREEN, PB_ORANGE),
        ];
    }
}
