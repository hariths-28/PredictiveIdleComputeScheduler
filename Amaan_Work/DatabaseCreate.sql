CREATE DATABASE compute_scheduler;
USE compute_scheduler;

-- Tracks who is online and available
CREATE TABLE nodes (
    ip_address VARCHAR(15) PRIMARY KEY,
    current_status VARCHAR(10), -- 'IDLE', 'BUSY', or 'OFFLINE'
    cpu_usage FLOAT,
    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Tracks the actual work being passed around
CREATE TABLE jobs (
    job_id INT AUTO_INCREMENT PRIMARY KEY,
    assigned_to_ip VARCHAR(15),
    status VARCHAR(15), -- 'PENDING', 'RUNNING', 'COMPLETED'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);