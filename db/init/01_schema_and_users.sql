-- ============================================================================
-- University of Vavuniya LMS — Local MySQL 8.x + MySQL Workbench Setup Script
-- ============================================================================
-- Run this script once in MySQL Workbench connected as 'root' (localhost:3306).
-- ============================================================================

CREATE DATABASE IF NOT EXISTS lms
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS test_lms
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

-- Application & migration user for local development
CREATE USER IF NOT EXISTS 'lms'@'localhost' IDENTIFIED BY 'lms1234';
CREATE USER IF NOT EXISTS 'lms'@'127.0.0.1' IDENTIFIED BY 'lms1234';
CREATE USER IF NOT EXISTS 'lms'@'%' IDENTIFIED BY 'lms1234';

GRANT ALL PRIVILEGES ON lms.*      TO 'lms'@'localhost';
GRANT ALL PRIVILEGES ON test_lms.* TO 'lms'@'localhost';
GRANT ALL PRIVILEGES ON lms.*      TO 'lms'@'127.0.0.1';
GRANT ALL PRIVILEGES ON test_lms.* TO 'lms'@'127.0.0.1';
GRANT ALL PRIVILEGES ON lms.*      TO 'lms'@'%';
GRANT ALL PRIVILEGES ON test_lms.* TO 'lms'@'%';

FLUSH PRIVILEGES;

-- Useful MySQL Workbench verification queries:
-- SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME
--   FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = 'lms';
