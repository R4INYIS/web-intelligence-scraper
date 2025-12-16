# 🔍 Web Intelligence Scraper

High-performance asynchronous web scraper that extracts business intelligence from domains: metadata, emails, social media profiles, and technology stack detection.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

- 🚀 **High Performance**: 50 concurrent workers with asyncio
- 🔄 **Queue-based Architecture**: Redis for distributed task management
- 🗄️ **Database Integration**: MySQL for persistent storage
- 🌐 **Browser Impersonation**: Bypass bot detection with curl_cffi
- 🛡️ **Robust Error Handling**: Auto-reconnection and retry logic
- 📊 **Real-time Progress Tracking**: Monitor processing status
- 🔍 **Technology Detection**: Identifies CMS, frameworks, and marketing tools
- 📧 **Contact Extraction**: Emails and social media profiles
- 🏪 **E-commerce Detection**: Flags online stores automatically

## 🎯 What It Extracts

| Data Type | Description |
|-----------|-------------|
| **Status Code** | HTTP response code |
| **Title** | Page title (cleaned & validated) |
| **Description** | Meta description (up to 500 chars) |
| **Emails** | Up to 5 validated emails (spam-filtered) |
| **Social Media** | Facebook, Instagram, LinkedIn, Twitter/X |
| **Tech Stack** | WordPress, Shopify, React, Vue, Angular, etc. |
| **E-commerce** | Automatically identifies online stores |
| **Marketing Tools** | Google Analytics, Facebook Pixel, TikTok Pixel, Hotjar, etc. |

## 🏗️ Architecture

```
┌─────────────┐      ┌─────────────┐      ┌─────────────────┐
│   MySQL     │─────▶│    Redis    │─────▶│   50 Workers    │
│  (Domains)  │      │   (Queue)   │      │   (Async I/O)   │
└─────────────┘      └─────────────┘      └────────┬────────┘
                                                    │
                                                    ▼
                                           ┌─────────────────┐
                                           │     MySQL       │
                                           │   (Results)     │
                                           └─────────────────┘
```

**Flow:**
1. `load_redis.py` loads unprocessed domains from MySQL to Redis queue
2. 50 async workers pull domains from Redis
3. Each worker fetches, parses, and analyzes the domain
4. Results are saved back to MySQL with retry logic

## 🐳 Docker Deployment

This project runs entirely in Docker containers for easy deployment and isolation.

### Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- 2GB RAM minimum
- 10GB disk space

### Quick Start

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/web-intelligence-scraper.git
cd web-intelligence-scraper
```

2. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your database credentials
```

3. **Start Docker services**
```bash
docker-compose up -d
```

4. **Verify services are running**
```bash
docker-compose ps
```

5. **Load domains into Redis queue**
```bash
docker exec -it scraper-app python scripts/load_redis.py
```

6. **Start processing**
```bash
docker exec -it scraper-app python scripts/main.py
```

## ⚙️ Configuration

### Main Settings (`scripts/main.py`)

```python
CONCURRENCY_LIMIT = 50          # Number of parallel workers
REQUEST_TIMEOUT = 15            # HTTP request timeout (seconds)
HARD_TIMEOUT = 45               # Maximum time per domain
MAX_DOWNLOAD_SIZE = 3 * 1024 * 1024  # Skip pages larger than 3MB
```

### Database Configuration

Edit the configuration in both scripts:

```python
DB_CONFIG = {
    'host': 'db',
    'user': 'root',
    'password': 'your_password',
    'database': 'your_db_name'
}

TABLE_NAME = 'your_tableName'
REDIS_KEY = 'cola_dominios'
```

## 📊 Performance

- **Speed**: ~1,000-2,000 domains/hour (network dependent)
- **Concurrency**: 50 workers processing in parallel
- **Memory**: ~500MB-1GB RAM usage
- **Efficiency**: Async I/O prevents blocking
- **Reliability**: Auto-retry on failures

### Performance Tips

- Increase `CONCURRENCY_LIMIT` for faster processing (requires more RAM)
- Adjust `REQUEST_TIMEOUT` based on target sites
- Use SSD storage for better MySQL performance
- Deploy on cloud with good network connectivity

## 🔧 Database Schema

Required MySQL table structure:

```sql
CREATE TABLE your_table (
    id INT PRIMARY KEY AUTO_INCREMENT,
    dominios VARCHAR(255) NOT NULL,
    status_code INT DEFAULT 0,
    title VARCHAR(255),
    description TEXT,
    emails JSON,
    socials JSON,
    tech_stack JSON,
    is_ecommerce TINYINT(1) DEFAULT 0,
    has_ads TINYINT(1) DEFAULT 0,
    last_checked DATETIME,
    INDEX idx_status (status_code),
    INDEX idx_ecommerce (is_ecommerce),
    INDEX idx_ads (has_ads)
);
```

## 📝 Usage Examples

### Basic Workflow

```bash
# 1. Load domains from MySQL to Redis
docker exec -it scraper-app python scripts/load_redis.py

# 2. Start scraping
docker exec -it scraper-app python scripts/main.py

# 3. Monitor progress in real-time
# Logs show progress every 100 domains
```

### Monitoring

```bash
# Check Redis queue size
docker exec -it redis redis-cli LLEN cola_dominios

# Check processed count
docker exec -it mysql mysql -u root -p -e \
  "SELECT COUNT(*) FROM db.table WHERE status_code > 0"

# View successful scrapes
docker exec -it mysql mysql -u root -p -e \
  "SELECT dominios, title, is_ecommerce FROM db.table WHERE status_code = 200 LIMIT 10"

# Check for errors
docker exec -it mysql mysql -u root -p -e \
  "SELECT status_code, COUNT(*) as count FROM db.table GROUP BY status_code"
```

### Reprocess Failed Domains

```sql
-- Reset failed domains for retry
UPDATE db.table SET status_code = 0 WHERE status_code != 200;
```

Then reload the queue and restart the scraper.

## 🛡️ Error Handling

The scraper includes comprehensive error handling:

### Connection Issues
- ✅ **Auto-reconnection**: Redis and MySQL connections auto-recover
- ✅ **Exponential backoff**: Gradual retry delays
- ✅ **Graceful degradation**: Workers continue on partial failures

### Data Validation
- ✅ **Email filtering**: Removes spam/placeholder emails
- ✅ **Social media validation**: Filters share buttons
- ✅ **Domain format checking**: Validates before processing
- ✅ **Title/description cleaning**: Removes errors and invalid content

### Resource Management
- ✅ **Timeout protection**: Hard limits prevent hanging
- ✅ **Memory cleanup**: Explicit deletion of large objects
- ✅ **Connection pooling**: Efficient resource usage
- ✅ **Graceful shutdown**: Proper cleanup on stop

## 🧪 Testing

### Test with Small Batch

```bash
# Reset 100 domains for testing
docker exec -it mysql mysql -u root -p webs -e \
  "UPDATE españa2 SET status_code = 0 LIMIT 100"

# Load and process
docker exec -it scraper-app python scripts/load_redis.py
docker exec -it scraper-app python scripts/main.py
```

### Verify Results

```sql
-- Check results
SELECT 
    status_code,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
FROM table
WHERE last_checked > DATE_SUB(NOW(), INTERVAL 1 HOUR)
GROUP BY status_code;
```

## 📦 Technology Stack

| Component | Technology |
|-----------|------------|
| **Language** | Python 3.9+ |
| **Async Framework** | asyncio |
| **HTTP Client** | curl-cffi (browser impersonation) |
| **HTML Parser** | BeautifulSoup4 |
| **Queue** | Redis |
| **Database** | MySQL 8.0 |
| **Containerization** | Docker & Docker Compose |

### Python Dependencies

```txt
asyncio>=3.4.3
beautifulsoup4>=4.12.0
curl-cffi>=0.6.0
mysql-connector-python>=8.2.0
redis>=5.0.0
lxml>=4.9.0
```

## 🔍 Technology Detection

The scraper identifies:

### CMS Platforms
- WordPress, Shopify, PrestaShop, Wix, Squarespace, Magento, Joomla, Drupal

### JavaScript Frameworks
- React, Vue.js, Angular, Next.js, Nuxt.js

### CSS Frameworks
- Bootstrap, Tailwind CSS

### Marketing & Analytics
- Google Analytics, Facebook Pixel, Google Ads, TikTok Pixel, Hotjar, Klaviyo

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style

- Follow PEP 8 guidelines
- Add docstrings to functions
- Include type hints where appropriate
- Write descriptive commit messages

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This tool is for educational and research purposes. Always:

- ✅ Respect `robots.txt` directives
- ✅ Follow website terms of service
- ✅ Implement appropriate rate limiting
- ✅ Use responsibly and ethically
- ❌ Don't use for unauthorized data harvesting
- ❌ Don't overload target servers

## 🙋 Support

For issues and questions:

- 🐛 [Open an Issue](https://github.com/R4INYIS/web-intelligence-scraper/issues)
- 💬 [Join Discussions](https://github.com/R4INYIS/web-intelligence-scraper/discussions)
- 📧 Email: contacto@rainyisdev.cc

## 📈 Roadmap

- [ ] Export results to CSV/JSON
- [ ] Web dashboard for real-time monitoring
- [ ] API endpoint for on-demand queries
- [ ] Multi-language content detection
- [ ] Machine learning for site classification
- [ ] Screenshot capture capability
- [ ] WHOIS data integration
- [ ] Sitemap parsing
- [ ] Robots.txt compliance checker

## 🌟 Acknowledgments

Built with:
- [curl-cffi](https://github.com/yifeikong/curl_cffi) for browser impersonation
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) for HTML parsing
- [Redis](https://redis.io/) for queue management
- [MySQL](https://www.mysql.com/) for data persistence

---

**Made with ❤️ for data intelligence and web research**

*Star ⭐ this repo if you find it useful!*

