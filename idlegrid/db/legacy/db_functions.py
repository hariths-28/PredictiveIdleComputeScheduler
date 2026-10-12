import mysql.connector
from mysql.connector import Error

# --- CONFIGURATION ---
# Update this with your actual MySQL password!
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'amaan', #Not yet able to use with other laptops
    'database': 'compute_scheduler'
}

def get_connection():
    """Creates and returns a connection to the database."""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def update_node(ip, status, cpu):
    """Updates a laptop's status, or adds it if it's new."""
    conn = get_connection()
    if conn:
        cursor = conn.cursor()
        # This SQL handles both new laptops and updating existing ones
        sql = """
            INSERT INTO nodes (ip_address, current_status, cpu_usage)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE 
            current_status = VALUES(current_status), 
            cpu_usage = VALUES(cpu_usage),
            last_heartbeat = CURRENT_TIMESTAMP
        """
        cursor.execute(sql, (ip, status, cpu))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"Node {ip} updated successfully.")

def get_available_node():
    """Finds one laptop that is currently IDLE."""
    conn = get_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT ip_address FROM nodes WHERE current_status = 'IDLE' LIMIT 1"
        cursor.execute(sql)
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            return result['ip_address']
        return None

def assign_job(ip):
    """Creates a new job and assigns it to a specific laptop."""
    conn = get_connection()
    if conn:
        cursor = conn.cursor()
        sql = "INSERT INTO jobs (assigned_to_ip, status) VALUES (%s, 'PENDING')"
        cursor.execute(sql, (ip,))
        conn.commit()
        job_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return job_id

# --- TESTING BLOCK ---
# If you run this file directly, it will test your database connection
if __name__ == "__main__":
    print("Testing Database Connection...")
    
    # 1. Simulate two laptops reporting in
    update_node("192.168.1.5", "IDLE", 15.2)
    update_node("192.168.1.10", "BUSY", 89.9)
    
    # 2. Try to find a free laptop
    free_laptop = get_available_node()
    print(f"Found free laptop: {free_laptop}")
    
    # 3. Assign a fake job to it
    if free_laptop:
        new_job_id = assign_job(free_laptop)
        print(f"Assigned Job #{new_job_id} to {free_laptop}")