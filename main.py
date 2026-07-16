import os
import logging
import requests
from datetime import datetime
from supabase import create_client, Client
from redeemer import redeem_code_for_all_players

# ─── Config ────────────────────────────────────────────────────────────────────
API_URL          = "https://kingshot.net/api/gift-codes"
PLAYER_IDS_FILE  = "playerIDs.txt"

# Load Supabase credentials from environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables!")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
# ───────────────────────────────────────────────────────────────────────────────

# Set up logging to both console and file
os.makedirs("logs", exist_ok=True)
log_filename = f"logs/run_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


def load_player_ids() -> list:
    """Read player IDs from playerIDs.txt (one ID per line, optional name after space)."""
    players = []
    if not os.path.exists(PLAYER_IDS_FILE):
        log.error(f"'{PLAYER_IDS_FILE}' not found! Please create it.")
        return players
    with open(PLAYER_IDS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(maxsplit=1)
            pid  = parts[0]
            name = parts[1] if len(parts) > 1 else pid
            players.append((pid, name))
    return players


def fetch_active_codes() -> list:
    """Call the KingShot API and return list of active gift code strings."""
    try:
        response = requests.get(API_URL, timeout=15)
        response.raise_for_status()
        data = response.json()
        codes = data.get("data", {}).get("giftCodes", [])
        return [c["code"] for c in codes if c.get("code")]
    except requests.RequestException as e:
        log.error(f"Failed to fetch gift codes from API: {e}")
        return []


def get_already_redeemed_pids(code: str) -> set:
    """Fetch all player IDs from Supabase who already redeemed this specific code."""
    try:
        response = supabase.table("redeemed_history") \
            .select("player_id") \
            .eq("gift_code", code) \
            .execute()
        return {row["player_id"] for row in response.data}
    except Exception as e:
        log.error(f"Failed to fetch tracking history from Supabase: {e}")
        return set()


def record_successful_redemptions(code: str, successful_pids: list):
    """Save the newly successful redemptions directly into the Supabase database."""
    if not successful_pids:
        return
    
    data_to_insert = [
        {"gift_code": code, "player_id": pid} for pid in successful_pids
    ]
    
    try:
        supabase.table("redeemed_history").insert(data_to_insert).execute()
        log.info(f"Successfully recorded {len(successful_pids)} entries to Supabase cloud.")
    except Exception as e:
        log.error(f"Failed to write redemptions to Supabase: {e}")


def check_and_redeem():
    """Core job: check for new codes and redeem them using granular cloud tracking."""
    log.info("─── Checking for new gift codes ───")

    active_codes = fetch_active_codes()
    if not active_codes:
        log.info("No active codes returned from API.")
        return

    log.info(f"API returned {len(active_codes)} active code(s): {active_codes}")

    player_ids = load_player_ids()
    if not player_ids:
        log.warning("No player IDs loaded — skipping redemption.")
        return

    log.info(f"Loaded {len(player_ids)} total target players from config.")

    for code in active_codes:
        # Check database per code to see who has already claimed it
        used_pids = get_already_redeemed_pids(code)

        # Only process players whose IDs are missing from Supabase for this code
        players_to_redeem = [
            (pid, name) for pid, name in player_ids 
            if pid not in used_pids
        ]

        if not players_to_redeem:
            log.info(f"Code [{code}]: Already processed for all active players.")
            continue

        log.info(f"\n{'='*50}")
        log.info(f"🎁 Processing code [{code}] for {len(players_to_redeem)} pending player(s)...")
        log.info(f"{'='*50}")
        
        # Execute Selenium orchestration
        successful_pids = redeem_code_for_all_players(code, players_to_redeem, log)
        
        # Save winners to Supabase database context
        record_successful_redemptions(code, successful_pids)
            
        log.info(f"✅ Finished processing code cycle: {code}")

    log.info("─── Check complete ───\n")


def main():
    log.info("╔══════════════════════════════════════╗")
    log.info("║  KingShot Auto Gift Code Redeemer    ║")
    log.info("╚══════════════════════════════════════╝")
    log.info(f"Player file : {PLAYER_IDS_FILE}")
    log.info("Storage Env : Supabase Cloud Backend")

    check_and_redeem()


if __name__ == "__main__":
    main()