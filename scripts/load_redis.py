import redis
import mysql.connector
import logging

# Configuration
REDIS_HOST = 'redis'  # Service name in docker-compose
DB_CONFIG = {
    'host': 'db',  # MySQL service name in docker-compose
    'user': 'root',
    'password': '-',
    'database': 'webs'
}
TABLE_NAME = ''
REDIS_KEY = 'cola_dominios'
BATCH_SIZE = 1000

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_queue():
    """Load unprocessed domains from MySQL into Redis queue."""
    r = None
    conn = None
    cursor = None
    
    try:
        # Connect to Redis and clear previous queue for safety
        logger.info("Connecting to Redis...")
        r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
        r.ping()
        
        # Check current queue size
        current_size = r.llen(REDIS_KEY)
        if current_size > 0:
            logger.warning(f"Queue '{REDIS_KEY}' contains {current_size} items. Clearing...")
            r.delete(REDIS_KEY)
        
        # Connect to MySQL
        logger.info("Connecting to MySQL...")
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        logger.info("📖 Reading domains from MySQL...")
        # Select only unprocessed domains (status_code is NULL or 0)
        cursor.execute(f"SELECT id, dominios FROM {TABLE_NAME} WHERE status_code = 0 OR status_code IS NULL")
        
        count = 0
        skipped = 0
        batch = []
        
        # Iterate and push to Redis in batches
        for (id_dom, dominio) in cursor:
            # Validate data before adding
            if not dominio or not str(dominio).strip():
                skipped += 1
                continue
            
            # Store in "ID|DOMAIN" format to avoid DB lookups in workers
            batch.append(f"{id_dom}|{dominio.strip()}")
            count += 1
            
            if len(batch) >= BATCH_SIZE:
                r.rpush(REDIS_KEY, *batch)
                batch = []
                logger.info(f"📤 Pushed {count} domains...")
                
        # Push remaining batch
        if batch:
            r.rpush(REDIS_KEY, *batch)
            
        logger.info(f"✅ Done! {count} domains loaded into Redis (key: '{REDIS_KEY}')")
        if skipped > 0:
            logger.warning(f"⚠️  Skipped {skipped} invalid domains")
            
    except redis.exceptions.ConnectionError as e:
        logger.error(f"❌ Redis connection error: {e}")
        raise
    except mysql.connector.Error as e:
        logger.error(f"❌ MySQL error: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        raise
    finally:
        # Clean up connections
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            logger.info("MySQL connection closed")

if __name__ == "__main__":
    try:
        load_queue()
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        exit(1)
