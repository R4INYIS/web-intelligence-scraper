import asyncio
import re
import json
import logging
import random
import time
import redis
import sys
import mysql.connector
from urllib.parse import urlparse, urlunparse
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup

# Configuration
DB_NAME = '-'
TABLE_NAME = '-'
REDIS_KEY = 'cola_dominios'
CONCURRENCY_LIMIT = 50  
REQUEST_TIMEOUT = 15
HARD_TIMEOUT = 45
MAX_DOWNLOAD_SIZE = 3 * 1024 * 1024

REDIS_CONFIG = {
    'host': 'redis', 
    'port': 6379, 
    'decode_responses': True
}

DB_CONFIG = {
    'host': 'db',
    'user': 'root',       
    'password': '-',  
    'database': DB_NAME,    
    'autocommit': True
}

# Progress tracking
processed_count = 0
processed_lock = asyncio.Lock()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Constants and filters
SPAM_EMAILS = {'info@example.com', 'admin@example.com', 'test@test.com', 'noreply@', 'no-reply@'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.bmp'}
PLACEHOLDER_PATTERNS = [
    'yourmail', 'youremail', 'your-email', 'your.email', 'your_email',
    'yourdomain', 'example@', '@example', 'mail@domain', 
    'email@domain', 'name@domain', 'contact@domain',
    'info@domain', 'admin@domain', 'placeholder', 'sample@', 'test@domain'
]

TECH_SIGNATURES = {
    "CMS": {
        "WordPress": ["wp-content", "wp-includes"],
        "Shopify": ["myshopify.com", "shopify.cdn"],
        "PrestaShop": ["prestashop"],
        "Wix": ["wix.com", "wix-image"],
        "Squarespace": ["squarespace"],
        "Magento": ["mage/cookies", "static/version"],
        "Joomla": ["joomla"],
        "Drupal": ["drupal", "sites/default/files"]
    },
    "Frameworks": {
        "React": ["react", "_react", "data-reactroot"],
        "Vue.js": ["vue.js", "data-v-", "vue.global"],
        "Angular": ["ng-version", "angular"],
        "Next.js": ["_next/static", "__next"],
        "Nuxt.js": ["_nuxt/", "__nuxt"],
        "Bootstrap": ["bootstrap.min.css", "bootstrap.min.js"],
        "Tailwind": ["tailwindcss", "tailwind.css"],
        "Google Analytics": ["googletagmanager.com", "ga(", "gtag/js"],
    },
    "Marketing": {
        "Facebook Pixel": ["fbevents.js", "fbq("],
        "Google Ads": ["googleads", "adsbygoogle"],
        "TikTok Pixel": ["ttq.load", "analytics.tiktok.com"],
        "Hotjar": ["hotjar.com", "_hjid"],
        "Klaviyo": ["klaviyo"]
    }
}


def clean_domain_input(raw_domain):
    """Clean and extract host from raw domain input."""
    if not raw_domain: return ""
    if "://" not in raw_domain:
        raw_domain = f"http://{raw_domain}"
    parsed = urlparse(raw_domain)
    return parsed.netloc

def is_valid_email(email):
    """Validate email against common spam and placeholder patterns."""
    if not email: return False
    email_lower = email.lower()
    if '%' in email: return False
    if any(p in email_lower for p in PLACEHOLDER_PATTERNS): return False
    if any(email_lower.endswith(ext) for ext in IMAGE_EXTENSIONS): return False
    if any(spam in email_lower for spam in SPAM_EMAILS): return False
    if '@' not in email or '.' not in email.split('@')[-1]: return False
    if len(email) < 5 or len(email) > 254: return False
    return True

def is_valid_social_link(url, platform):
    """Validate social media link for given platform."""
    url_lower = url.lower()
    exclude = ['sharer', 'share', 'intent/tweet', 'share.php']
    if any(p in url_lower for p in exclude): return False
    
    if platform == 'facebook': return 'facebook.com/' in url_lower and len(url) > 20
    elif platform == 'instagram': return 'instagram.com/' in url_lower and len(url) > 20
    elif platform == 'linkedin': return 'linkedin.com/' in url_lower and len(url) > 20
    elif platform == 'twitter': return ('twitter.com/' in url_lower or 'x.com/' in url_lower)
    return True

def validate_data(title, description):
    """Basic validation and cleaning of title and description."""
    if title and len(title.strip()) < 3: title = ""
    error_titles = ['404', 'error', 'not found', 'forbidden']
    if title and any(err in title.lower() for err in error_titles): title = ""
    if description and len(description.strip()) < 10: description = ""
    return title, description

async def analyze_domain(session, domain_id, raw_domain):
    """Analyze a domain: fetch HTML, extract metadata, emails, socials, and detect technologies."""
    await asyncio.sleep(random.uniform(0.1, 0.5))
    
    clean_host = clean_domain_input(raw_domain)
    if not clean_host:
        return (0, "Invalid Domain", None, None, None, None, 0, 0, domain_id)
    
    # Try multiple URL variations: HTTPS first, then HTTP, then www subdomain
    candidates = [
        urlunparse(('https', clean_host, '', '', '', '')),
        urlunparse(('http', clean_host, '', '', '', '')),
        urlunparse(('https', f"www.{clean_host}", '', '', '', ''))
    ]

    response = None
    
    for url in candidates:
        try:
            resp = await session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True, max_redirects=3)
            if resp.status_code > 0:
                # Skip pages larger than 3MB to avoid memory issues
                cl = resp.headers.get('content-length')
                if cl and int(cl) > MAX_DOWNLOAD_SIZE:
                    return (resp.status_code, "Page Too Large", None, None, None, None, 0, 0, domain_id)
                response = resp
                break
        except Exception:
            continue

    if not response:
        return (0, "Connection Failed", None, None, None, None, 0, 0, domain_id)

    status = response.status_code

    try:
        html = response.text
        if not html: return (status, "Empty", None, None, None, None, 0, 0, domain_id)
        
        soup = BeautifulSoup(html, 'html.parser')
        html_lower = html.lower()

        # Extract title
        title_tag = soup.title
        title = title_tag.string[:250].replace("\n", "").strip() if title_tag and title_tag.string else ""

        # Extract description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        description = meta_desc.get("content")[:500] if meta_desc else ""
        
        title, description = validate_data(title, description)

        # Detect technologies and categorize
        # Scan HTML for tech signatures and set flags for ecommerce/ads
        detected_tech = []
        is_ecomm = 0
        has_ads = 0
        
        for category, techs in TECH_SIGNATURES.items():
            for tech_name, signatures in techs.items():
                if any(sig in html_lower for sig in signatures):
                    detected_tech.append(tech_name)
                    if category == "Marketing": has_ads = 1
                    if tech_name in ["Shopify", "PrestaShop", "Magento", "WooCommerce"]: is_ecomm = 1
        
        if "woocommerce" in html_lower:
            if "WordPress" not in detected_tech: detected_tech.append("WordPress")
            is_ecomm = 1

        # Extract and validate emails (limit to 5 to avoid spam lists)
        raw_emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
        valid_emails = [e for e in set(raw_emails) if is_valid_email(e)][:5]

        # Extract social media links (filter out share buttons and invalid profiles)
        socials = {}
        for link in soup.find_all('a', href=True):
            h = link['href']
            if not h.startswith('http'): continue
            h_low = h.lower()
            if "facebook.com" in h_low and is_valid_social_link(h, 'facebook'): socials['facebook'] = h
            elif "instagram.com" in h_low and is_valid_social_link(h, 'instagram'): socials['instagram'] = h
            elif "linkedin.com" in h_low and is_valid_social_link(h, 'linkedin'): socials['linkedin'] = h
            elif ("twitter.com" in h_low or "x.com" in h_low) and is_valid_social_link(h, 'twitter'): socials['twitter'] = h

        # Free memory before returning (important for high concurrency)
        del html, soup, html_lower
        
        return (status, title, description, json.dumps(valid_emails), json.dumps(socials), json.dumps(list(set(detected_tech))), is_ecomm, has_ads, domain_id)

    except Exception as e: 
        return (status, "Parse Error", None, None, None, None, 0, 0, domain_id)


async def redis_worker(worker_id, session):
    """Worker that processes domains from Redis queue and updates database."""
    logger.info(f"👷 Worker {worker_id} ready.")
    
    # Initialize variables to avoid UnboundLocalError in finally block
    r = None
    db_conn = None
    cursor = None
    
    try:
        r = redis.Redis(**REDIS_CONFIG)
    except Exception as e:
        logger.error(f"Worker {worker_id} Redis error: {e}")
        return

    try:
        db_conn = mysql.connector.connect(**DB_CONFIG)
        cursor = db_conn.cursor()
    except Exception as e:
        logger.error(f"Worker {worker_id} error MySQL: {e}")
        return

    try:
        while True:
            try:
                # Blocking pop: waits up to 5 seconds for new items in queue
                item = r.blpop(REDIS_KEY, timeout=5)
                
                if not item:
                    continue 
                
                val = item[1]
                try:
                    d_id, d_name = val.split('|', 1)
                    d_id = int(d_id)  # Validate domain_id is numeric
                except (ValueError, TypeError):
                    logger.warning(f"Invalid format in queue: {val}")
                    continue

                try:
                    res = await asyncio.wait_for(
                        analyze_domain(session, d_id, d_name), 
                        timeout=HARD_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"💀 Hard timeout on {d_name}. Skipping...")
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error processing {d_name}: {e}")
                    continue

                # Update database with retry logic (handles transient connection issues)
                sql = f"""
                    UPDATE {TABLE_NAME} 
                    SET status_code=%s, title=%s, description=%s, emails=%s, socials=%s, 
                        tech_stack=%s, is_ecommerce=%s, has_ads=%s, last_checked=NOW() 
                    WHERE id=%s
                """
                
                saved = False
                # Retry up to 3 times on MySQL errors
                for attempt in range(3):
                    try:
                        cursor.execute(sql, res)
                        db_conn.commit()
                        saved = True
                        break
                    except mysql.connector.Error as e:
                        logger.warning(f"MySQL error (attempt {attempt+1}/3): {e}")
                        # Try to reconnect: first attempt reconnect, then create new connection
                        try:
                            db_conn.reconnect(attempts=1, delay=0)
                        except Exception as reconnect_err:
                            logger.error(f"Error reconnecting MySQL: {reconnect_err}")
                            try:
                                db_conn = mysql.connector.connect(**DB_CONFIG)
                            except:
                                await asyncio.sleep(2)
                                continue
                        cursor = db_conn.cursor()
                        await asyncio.sleep(1)
                
                if not saved:
                    logger.error(f"❌ Failed to save {d_name} after 3 attempts")
                else:
                    # Update progress counter
                    global processed_count
                    async with processed_lock:
                        processed_count += 1
                        if processed_count % 100 == 0:
                            logger.info(f"📊 Progress: {processed_count} domains processed")
                
                if res[0] == 200:
                    logger.info(f"✅ {d_name} OK")

            except redis.exceptions.ConnectionError:
                logger.warning(f"Worker {worker_id} Redis connection lost, reconnecting...")
                await asyncio.sleep(5)
                try: 
                    r = redis.Redis(**REDIS_CONFIG)
                except Exception as reconnect_err:
                    logger.error(f"Failed to reconnect Redis: {reconnect_err}")
                    break
                
            except Exception as e:
                logger.error(f"🔥 Worker {worker_id} loop error: {e}")
                await asyncio.sleep(1)
    
    except KeyboardInterrupt:
        logger.info(f"Worker {worker_id} interrupted")
    
    finally:
        # Ensure database connections are properly closed on worker shutdown
        try:
            if cursor:
                cursor.close()
            if db_conn and db_conn.is_connected():
                db_conn.close()
            logger.info(f"Worker {worker_id} closed cleanly")
        except Exception as e:
            logger.error(f"Error closing worker {worker_id}: {e}")

async def main():
    """Main orchestrator: starts workers and manages the scraping process."""
    logger.info(f"🚀 Starting orchestrator. Timeout: {REQUEST_TIMEOUT}s. Concurrency: {CONCURRENCY_LIMIT}")
    
    # Verify Redis connection before starting workers
    try:
        r_test = redis.Redis(**REDIS_CONFIG)
        r_test.ping()
    except Exception as e:
        logger.critical(f"❌ Redis error: {e}")
        return

    # Create session with browser impersonation and spawn worker tasks
    async with AsyncSession(impersonate="firefox135", verify=False) as session:
        tasks = []
        for i in range(CONCURRENCY_LIMIT):
            tasks.append(asyncio.create_task(redis_worker(i, session)))
        
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Stop.")
        finally:
            logger.info(f"✅ Orchestrator finished. Total processed: {processed_count} domains")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
