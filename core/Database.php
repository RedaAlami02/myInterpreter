<?php
require_once __DIR__ . '/../config/config.php';

class Database {
    private ?PDO $state = null;

    public function opendb(): PDO {
        if ($this->state !== null) return $this->state;

        try {
            $dsn = sprintf(
                'mysql:host=%s;dbname=%s;port=%s;charset=utf8mb4',
                DB_HOST, DB_NAME, DB_PORT
            );
            $this->state = new PDO($dsn, DB_USER, DB_PASS, [
                PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                PDO::ATTR_EMULATE_PREPARES   => false,
            ]);
        } catch (PDOException $e) {
            http_response_code(500);
            die('Database connection failed: ' . $e->getMessage());
        }
        return $this->state;
    }
}
