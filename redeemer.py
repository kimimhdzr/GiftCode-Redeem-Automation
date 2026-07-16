import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

SITE_URL = "https://ks-giftcode.centurygame.com/"

# Tuning parameters (seconds)
WAIT_TIMEOUT       = 15   
POST_LOGIN_WAIT    = 3    
POST_CONFIRM_WAIT  = 3    
BETWEEN_PLAYERS    = 2    


def build_driver(headless: bool = True) -> webdriver.Chrome:
    os.environ.setdefault("SE_CACHE_PATH", os.path.join(os.path.dirname(__file__), ".selenium_cache"))
    
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,800")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def wait_for_element(wait, by, value, description="element"):
    try:
        return wait.until(EC.presence_of_element_located((by, value)))
    except TimeoutException:
        raise TimeoutException(f"Timed out waiting for {description}")


def wait_for_clickable(wait, by, value, description="button"):
    try:
        return wait.until(EC.element_to_be_clickable((by, value)))
    except TimeoutException:
        raise TimeoutException(f"Timed out waiting for clickable {description}")


def get_result_message(driver, wait) -> str:
    selectors = [
        (By.XPATH, '//*[contains(@class,"result") or contains(@class,"toast") or contains(@class,"modal") or contains(@class,"tip") or contains(@class,"message")]'),
        (By.XPATH, '//div[contains(@class,"popup")]'),
        (By.XPATH, '//div[contains(@class,"dialog")]'),
    ]
    time.sleep(POST_CONFIRM_WAIT)
    for by, xpath in selectors:
        try:
            elements = driver.find_elements(by, xpath)
            for el in elements:
                text = el.text.strip()
                if text and len(text) > 3:
                    return text
        except Exception:
            continue
    return "(no result message captured)"


def redeem_single(driver, wait, pid: str, username: str, code: str, log) -> bool:
    log.info(f"  ▶ Player: {username} (ID: {pid})")

    try:
        driver.get(SITE_URL)

        player_input = wait_for_element(
            wait, By.XPATH, '//input[@placeholder="Player ID"]', "Player ID input"
        )
        player_input.clear()
        player_input.send_keys(pid)
        log.info(f"    Entered Player ID: {pid}")

        login_btn = wait_for_clickable(
            wait, By.XPATH, '//div[contains(@class,"login_btn") and contains(@class,"btn")]', "Login button"
        )
        login_btn.click()
        log.info("    Clicked Login.")

        try:
            wait.until(EC.invisibility_of_element_located((By.XPATH, '//*[contains(@class,"loading")]')))
        except TimeoutException:
            pass  

        wait_for_element(
            wait, By.XPATH, '//input[@placeholder="Enter Gift Code"]', "Gift Code input"
        )
        time.sleep(POST_LOGIN_WAIT)
        log.info("    Profile loaded.")

        code_input = driver.find_element(By.XPATH, '//input[@placeholder="Enter Gift Code"]')
        code_input.clear()
        code_input.send_keys(code)
        log.info(f"    Entered code: {code}")

        confirm_btn = wait_for_clickable(
            wait, By.XPATH, '//div[contains(@class,"exchange_btn") and contains(text(),"Confirm")]', "Confirm button"
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        log.info("    Clicked Confirm.")

        result_text = get_result_message(driver, wait)
        log.info(f"    Result text: {result_text}")

        result_lower = result_text.lower()
        failed_keywords = ["expired", "invalid", "error", "fail", "already", "used", "wrong"]
        is_success = not any(kw in result_lower for kw in failed_keywords)

        return is_success

    except TimeoutException as e:
        log.error(f"    [TIMEOUT] {e}")
        _save_screenshot(driver, pid, username, "timeout")
        return False
    except NoSuchElementException as e:
        log.error(f"    [ELEMENT NOT FOUND] {e}")
        _save_screenshot(driver, pid, username, "missing_element")
        return False
    except Exception as e:
        log.error(f"    [UNEXPECTED ERROR] {e}")
        _save_screenshot(driver, pid, username, "error")
        return False


def _save_screenshot(driver, pid, username, reason):
    try:
        os.makedirs("screenshots", exist_ok=True)
        fname = f"screenshots/debug_{pid}_{username}_{reason}.png"
        driver.save_screenshot(fname)
    except Exception:
        pass


def redeem_code_for_all_players(code: str, players: list, log) -> list:
    """
    Process runtime sequence.
    Returns a array of IDs that successfully processed to update Supabase.
    """
    # Change to headless=False here to debug visually on your local computer
    driver = build_driver(headless=True)
    wait = WebDriverWait(driver, WAIT_TIMEOUT)

    successful_pids = []
    start_time = time.time()

    try:
        for pid, username in players:
            success = redeem_single(driver, wait, pid, username, code, log)
            if success:
                log.info(f"    ✅ SUCCESS — {username} ({pid})")
                successful_pids.append(pid)
            else:
                log.warning(f"    ❌ FAILED  — {username} ({pid})")
            time.sleep(BETWEEN_PLAYERS)
    finally:
        driver.quit()

    elapsed = time.time() - start_time
    log.info(f"\n  Batch Complete for [{code}]:")
    log.info(f"  ✅ Tracked successes to dump: {len(successful_pids)}")
    log.info(f"  ⏱  Time elapsed: {elapsed:.1f}s")
    
    return successful_pids