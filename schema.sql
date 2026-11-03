-- Opcional: cria o banco e o usuario no MySQL. As tabelas sao criadas
-- automaticamente pela API na primeira execucao.
CREATE DATABASE IF NOT EXISTS energyguard CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'energyguard'@'%' IDENTIFIED BY 'troque_esta_senha';
GRANT ALL PRIVILEGES ON energyguard.* TO 'energyguard'@'%';
FLUSH PRIVILEGES;
