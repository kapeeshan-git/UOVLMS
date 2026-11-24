-- University of Vavuniya LMS: run once in MySQL Workbench as root (guide 14.4).
-- Change both passwords and put the 'lms' one in .env (DB_PASSWORD).

CREATE DATABASE IF NOT EXISTS lms
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- Application / migration user. Also owns test_lms, which `manage.py test` creates and drops.
CREATE USER IF NOT EXISTS 'lms'@'localhost' IDENTIFIED BY 'change-me';
GRANT ALL PRIVILEGES ON lms.*      TO 'lms'@'localhost';
GRANT ALL PRIVILEGES ON test_lms.* TO 'lms'@'localhost';

-- Optional production-style runtime user (DML only). For a strict append-only audit table,
-- grant per-table privileges instead (SELECT, INSERT only on lms.audit_auditevent).
-- CREATE USER IF NOT EXISTS 'lms_app'@'localhost' IDENTIFIED BY 'change-me-app';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON lms.* TO 'lms_app'@'localhost';

FLUSH PRIVILEGES;

-- Handy queries for the demo (run as lms, schema lms):
-- SELECT id, copy_id, active_copy_id, status, due_at FROM circulation_loan ORDER BY id DESC LIMIT 20;
-- SELECT type, status, attempts, run_at, error_category FROM notifications_job ORDER BY id DESC LIMIT 20;
-- SELECT * FROM performance_schema.data_locks;     -- row locks during the concurrency demo
-- SELECT IS_USED_LOCK('lms_scheduler');            -- which connection is the scheduler
