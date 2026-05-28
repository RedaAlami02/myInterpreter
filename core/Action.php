<?php
require_once __DIR__ . '/../config/config.php';

class Company {
    // Traffic-light labels
    const RESULT = ['green', 'orange', 'red'];

    public string $NAME  = '';
    public bool   $stored = false;

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
        return [
            'PER' => $this->PER < PER_GREEN ? $r[0] : ($this->PER < PER_ORANGE ? $r[1] : $r[2]),
            'PEG' => ($this->PEG > 0 && $this->PEG < PEG_GREEN)
                   ? $r[0]
                   : (($this->PEG > 0 && $this->PEG < PEG_ORANGE) ? $r[1] : $r[2]),
            'PR'  => $this->PR < PR_GREEN ? $r[0] : ($this->PR < PR_ORANGE ? $r[1] : $r[2]),
            'PB'  => $this->PB < PB_GREEN ? $r[0] : ($this->PB < PB_ORANGE ? $r[1] : $r[2]),
        ];
    }
}
