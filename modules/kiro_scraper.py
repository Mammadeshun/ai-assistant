import time
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

UNIPV_USERNAME  = os.environ.get("UNIPV_USERNAME", "")
UNIPV_PASSWORD  = os.environ.get("UNIPV_PASSWORD", "")
SAML2_LOGIN_URL = "https://elearning.unipv.it/auth/saml2/login.php?wants&idp=28c4b89f3ffa1f445c94d30f5ee49037&passive=off"

# State file to remember what we've already seen
STATE_FILE = "data/kiro_state.json"

COURSES = {
    "Computer Vision":                  "https://elearning.unipv.it/course/view.php?id=5877",
    "Machine Learning & Deep Learning": "https://elearning.unipv.it/course/view.php?id=10341",
    "Fuzzy Systems":                    "https://elearning.unipv.it/course/view.php?id=11127",
    "Statistical Modelling":            "https://elearning.unipv.it/course/view.php?id=7460",
    "Cognitive Psychology":             "https://elearning.unipv.it/course/view.php?id=4228",
    "Algorithms & Data Structures":     "https://elearning.unipv.it/course/view.php?id=5360",
    "Data Mining":                      "https://elearning.unipv.it/course/view.php?id=10353",
    "Statistical Signal Processing":    "https://elearning.unipv.it/course/view.php?id=9041",
    "Linear Algebra":                   "https://elearning.unipv.it/course/view.php?id=8778",
}

def load_state():
    """Load previously seen items from disk"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(state):
    """Persist the current seen items to disk"""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def login(driver):
    driver.get(SAML2_LOGIN_URL)
    time.sleep(3)
    username_field = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.XPATH, "//input[@type='text' or @id='username']"))
    )
    password_field = driver.find_element(By.XPATH, "//input[@type='password']")
    username_field.send_keys(UNIPV_USERNAME)
    password_field.send_keys(UNIPV_PASSWORD)
    time.sleep(1)
    driver.find_element(By.XPATH, "//button[@type='submit' or @name='_eventId_proceed']").click()
    time.sleep(5)

def get_all_course_items(driver, course_url):
    """Returns ALL activity items on a course page as a set of strings"""
    driver.get(course_url)
    time.sleep(3)
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    items = set()
    for activity in soup.find_all("li", class_="activity"):
        label = activity.find("span", class_="instancename")
        if label:
            text = label.text.strip()
            if text:
                items.add(text)
    return items

def check_kiro_updates():
    print("🎓 Connecting to Kiro UniPV...")
    
    # Load what we've already seen
    state = load_state()
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    try:
        print("   -> Logging in via SAML2...")
        login(driver)
        
        new_updates = {}
        new_state = {}
        
        print("   -> Checking each course for NEW items...")
        for course_name, course_url in COURSES.items():
            print(f"      Scanning: {course_name}...")
            
            current_items = get_all_course_items(driver, course_url)
            previously_seen = set(state.get(course_name, []))
            
            # Only items we haven't seen before
            truly_new = current_items - previously_seen
            
            if truly_new:
                new_updates[course_name] = sorted(truly_new)
            
            # Save everything we see now for next run
            new_state[course_name] = list(current_items)
        
        driver.quit()
        
        # Persist updated state to disk
        save_state(new_state)
        print("   -> State saved to data/kiro_state.json")
        
        return new_updates
        
    except Exception as e:
        print(f"❌ Kiro Scraper Error: {e}")
        driver.quit()
        return {}

def format_kiro_report(updates):
    if not updates:
        return "🎓 Kiro: No new materials or announcements today."
    
    report = "🎓 *KIRO — New Course Materials*\n"
    report += "━" * 28 + "\n"
    for course, items in updates.items():
        report += f"\n📚 *{course}*\n"
        for item in items:
            report += f"  📄 {item}\n"
    return report

if __name__ == "__main__":
    print("\n📚 Testing Kiro Scraper...")
    updates = check_kiro_updates()
    report = format_kiro_report(updates)
    print("\n" + report)
