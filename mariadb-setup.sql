-- Auf dem MariaDB LXC einmalig ausfuehren (z.B. via mysql -u root -p)
CREATE DATABASE IF NOT EXISTS calendar_sync CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'calendar_sync'@'%' IDENTIFIED BY 'HIER_SICHERES_PASSWORT';
GRANT ALL PRIVILEGES ON calendar_sync.* TO 'calendar_sync'@'%';
FLUSH PRIVILEGES;
