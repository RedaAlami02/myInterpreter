-- Database cleanup: consolidate duplicate tables and normalize to lowercase
-- This script should be run once to clean up the mixed-case table names

SET foreign_key_checks = 0;

-- 1. Drop old/duplicate lowercase tables (benefits is old schema without ID_USER)
DROP TABLE IF EXISTS benefits;
DROP TABLE IF EXISTS company;

-- 3. Rename uppercase tables to lowercase for consistency
RENAME TABLE ACHATS TO achats;
RENAME TABLE BENEFITS TO benefits;
RENAME TABLE COMPANY TO company;
RENAME TABLE DATA TO data;
RENAME TABLE FORMAT TO format;
RENAME TABLE PORTEFEUILLE TO portefeuille;
RENAME TABLE UTILISATEUR TO utilisateur;
RENAME TABLE VENTES TO ventes;

-- 4. Verify all tables are now lowercase
SELECT TABLE_NAME FROM information_schema.TABLES
WHERE TABLE_SCHEMA='stock'
ORDER BY TABLE_NAME;

SET foreign_key_checks = 1;
