# vendor_stock/scraper/config.py
import os
from dotenv import load_dotenv

# Load .env from the scraper directory
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

# DDécor
DDECOR_URL = "https://ddecor.my.site.com/Merchant/s/"
DDECOR_USERNAME = os.getenv("DDECOR_USERNAME", "cozycornerpatios@gmail.com")
DDECOR_PASSWORD = os.getenv("DDECOR_PASSWORD", "Fam@1234567")

# Agora
AGORA_EMAIL = os.getenv("AGORA_EMAIL", "factory@fabricsandmoreus.com")
AGORA_PASSWORD = os.getenv("AGORA_PASSWORD", "Sujan@123")

# Linen Craft
LC_URL = "https://linencraft-my.sharepoint.com/:x:/g/personal/accounts_linencraft_in/IQCKfCWXfITkQbuWsCTtqm8kAXv0w4ijCalOUxapNEnny6w?download=1"

# Mapping file
MAPPING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddecor_mapping.tsv")

# Email
EMAIL_RECIPIENTS = ["sahil@cozycornerpatios.com"]

# Thresholds
LOW_STOCK_THRESHOLD = 20
