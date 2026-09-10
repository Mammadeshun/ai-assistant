import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

chrome_options = Options()
chrome_options.add_argument("--no-sandbox")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
driver.get("https://elearning.unipv.it/login/index.php")
time.sleep(3)

# Print ALL buttons and links on the page
print("\n=== ALL BUTTONS ===")
for btn in driver.find_elements("tag name", "button"):
    print(f"BUTTON -> text: '{btn.text}' | id: '{btn.get_attribute('id')}' | class: '{btn.get_attribute('class')}'")

print("\n=== ALL LINKS ===")
for link in driver.find_elements("tag name", "a"):
    print(f"LINK -> text: '{link.text}' | href: '{link.get_attribute('href')}'")

input("Press ENTER to close the browser...")
driver.quit()
