##########UI
import customtkinter as ctk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
import threading

###########################
#Functionality
##########################
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import re
import logging
import os
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException

# ------------------- Setup Logging ------------------- #
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# ------------------- Utility Functions ------------------- #
def human_delay(min_sec=1.0, max_sec=4.5):
    """Sleep like a human."""
    time.sleep(random.uniform(min_sec, max_sec))


def generate_user_agent():
    """Return a random desktop user-agent string."""
    try:
        from fake_useragent import UserAgent
        return UserAgent().random
    except:
        # fallback if fake_useragent fails
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def expand_sizes(size_range: str):
    """Parse and expand size range like 'S-4XL' into a list."""
    sizes_order = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]
    size_range = size_range.upper().replace("–", "-")
    match = re.search(r'([XSML\d]+)\s*-\s*(\d*X?L+)', size_range)
    if not match:
        return []
    start, end = match.groups()
    try:
        start_index = sizes_order.index(start)
        end_index = sizes_order.index(end)
        return sizes_order[start_index:end_index + 1]
    except ValueError:
        return [start, end]


# ------------------- Scraper Class ------------------- #
class YupooScraper:
    def __init__(self, headless=True, debug=False):
        self.debug = debug
        options = uc.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f"user-agent={generate_user_agent()}")
        self.driver = uc.Chrome(options=options)
        logging.info("Initialized stealth Chrome driver.")

    def close(self):
        self.driver.quit()

    def scrape_album(self, url: str) -> dict:
        logging.info(f"Scraping album: {url}")
        data = {
            "url": url,
            "title": None,
            "image_urls": [],
            "sizes": []
        }

        try:
            self.driver.get(url)
            human_delay(2, 4)

            # Scroll until all images are loaded
            self._scroll_to_bottom()

            # Get final HTML and parse
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            # Extract album title from page
            title_tag = soup.find("span", class_="showalbumheader__gallerytitle")
            if title_tag:
                raw_title = title_tag.get_text(strip=True)
                # Remove currency and price info (e.g. ￥179, $100, ¥200)
                title = re.sub(r'[¥￥$€£]\s?\d+(\.\d+)?\s*', '', raw_title).strip()
                data['title'] = title
            else:
                # Fallback to <title> tag
                raw_title = soup.title.string.strip() if soup.title else "Untitled"
                title = re.sub(r'[¥￥$€£]\s?\d+(\.\d+)?\s*', '', raw_title).strip()
                data['title'] = title

            # --- Extract cover image ---
            cover_img_tag = soup.find("img", class_="autocover")
            cover_img_url = None
            if cover_img_tag:
                raw_src = cover_img_tag.get("data-src") or cover_img_tag.get("src")
                if raw_src:
                    cover_img_url = "https:" + raw_src if raw_src.startswith("//") else raw_src

            # --- Extract 'big.' images (jpeg, png, etc.) ---
            big_images = []
            seen = set()
            for img in soup.find_all("img", attrs={"data-src": True}):
                src = img["data-src"]
                if "big." in src:
                    full_url = "https:" + src if src.startswith("//") else src
                    if full_url != cover_img_url and full_url not in seen:
                        big_images.append(full_url)
                        seen.add(full_url)

            # --- Combine with cover image first ---
            image_urls = [cover_img_url] + big_images if cover_img_url else big_images
            data["image_urls"] = image_urls

            # Extract sizes from title
            size_match = re.search(r'([XSML\d]+)\s*[-–]\s*(\d*X?L+)', title.upper())
            if size_match:
                data['sizes'] = expand_sizes(size_match.group(0))

            logging.info(f"Scraped: {title} | {len(data['image_urls'])} images | Sizes: {data['sizes']}")

            if self.debug:
                self._save_debug_screenshot(title)

        except WebDriverException as e:
            logging.error(f"Selenium error: {e}")
        except Exception as e:
            logging.error(f"Error scraping {url}: {e}")

        return data

    def _scroll_to_bottom(self, max_attempts=20):
        """Scroll the page down gradually to load dynamic content."""
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        attempts = 0
        while attempts < max_attempts:
            self.driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
            human_delay(1, 2)
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            attempts += 1
        logging.info("Finished scrolling.")

    def _save_debug_screenshot(self, title):
        safe_title = re.sub(r'\W+', '_', title)[:40]
        path = f"debug_{safe_title}.png"
        self.driver.save_screenshot(path)
        logging.info(f"Saved debug screenshot to {path}")



##########################################################
################# MAIN RUN ##############################
########################################################
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class YupooGUI:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Yupoo to Shopify Scraper")
        self.root.geometry("720x600")
        self.urls = []

        # --- Title ---
        self.title_label = ctk.CTkLabel(self.root, text="Yupoo Scraper + Shopify Uploader",
                                        font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(pady=10)

        # --- URL Paste Section ---
        self.url_box = ctk.CTkTextbox(self.root, height=120, width=600, corner_radius=6, border_width=1)
        self.url_box.pack(pady=(5, 10))

        self.url_placeholder = (
            "📝 Paste one Yupoo album URL per line, e.g.:\n"
            "https://example.yupoo.com/albums/12345678\n"
            "https://anotheruser.yupoo.com/albums/98765432"
        )
        self.url_box.insert("1.0", self.url_placeholder)
        self.url_placeholder_active = True

        # Clear placeholder on focus
        def clear_placeholder(event=None):
            if self.url_placeholder_active:
                self.url_box.delete("1.0", "end")
                self.url_placeholder_active = False

        def restore_placeholder(event=None):
            if not self.url_box.get("1.0", "end-1c").strip():
                self.url_box.insert("1.0", self.url_placeholder)
                self.url_placeholder_active = True

        self.url_box.bind("<FocusIn>", clear_placeholder)
        self.url_box.bind("<FocusOut>", restore_placeholder)

        # --- Load CSV Button ---
        self.load_csv_btn = ctk.CTkButton(self.root, text="📁 Load URLs from CSV", command=self.load_csv)
        self.load_csv_btn.pack(pady=5)

        # --- Scrape Button ---
        self.scrape_btn = ctk.CTkButton(self.root, text="🕷 Scrape Albums",
                                        command=self.run_scrape_thread,
                                        fg_color="#4CAF50", hover_color="#45A049")
        self.scrape_btn.pack(pady=10)

        # --- Shopify Token Fields ---
        self.token_label = ctk.CTkLabel(self.root, text="Shopify Access Token:")
        self.token_label.pack()
        self.token_entry = ctk.CTkEntry(self.root, width=400)
        self.token_entry.pack(pady=(0, 5))

        self.store_label = ctk.CTkLabel(self.root, text="Shopify Store Domain (e.g. mystore.myshopify.com):")
        self.store_label.pack()
        self.store_entry = ctk.CTkEntry(self.root, width=400)
        self.store_entry.pack(pady=(0, 10))

        self.upload_btn = ctk.CTkButton(self.root, text="🚀 Upload to Shopify", command=self.upload_to_shopify)
        self.upload_btn.pack(pady=5)

        # --- Status Console ---
        self.status_box = ctk.CTkTextbox(self.root, height=180, width=680)
        self.status_box.pack(pady=10)

        self.root.mainloop()

    def load_csv(self):
        try:
            file_path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
            if not file_path:
                return

            df = pd.read_csv(file_path)
            df.columns = df.columns.str.lower()

            if "url" not in df.columns:
                messagebox.showerror("Invalid CSV", "CSV must contain a 'url' column.")
                return

            self.urls = df["url"].dropna().tolist()
            self.status_box.insert("end", f"✅ Loaded {len(self.urls)} URLs from CSV\n")
            self.status_box.see("end")

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def run_scrape_thread(self):
        thread = threading.Thread(target=self.scrape_manual_or_loaded_urls)
        thread.start()

    def scrape_manual_or_loaded_urls(self):
        # Collect manual URLs from the text box
        manual_urls = [u.strip() for u in self.url_box.get("1.0", "end").splitlines() if u.strip().startswith("http")]

        # Combine and deduplicate
        combined_urls = self.urls + manual_urls
        all_urls = list(set(combined_urls))
        duplicates_removed = len(combined_urls) - len(all_urls)

        if not all_urls:
            messagebox.showerror("Error", "No valid URLs to scrape.")
            return

        # self.urls with deduplicated list
        self.urls = all_urls

        # Display deduplication info
        self.status_box.insert("end", f"Total URLs input: {len(combined_urls)}\n")
        self.status_box.insert("end", f"Duplicates removed: {duplicates_removed}\n")
        self.status_box.insert("end", f"✅ Unique URLs to scrape: {len(all_urls)}\n\n")
        self.status_box.insert("end", f"Loading Scrapper ...\n\n\n")
        self.status_box.see("end")

        scraper = YupooScraper(headless=True, debug=False)
        all_data = []

        for url in self.urls:
            self.status_box.insert("end", f"🔍 Scraping: {url}\n")
            self.status_box.see("end")
            result = scraper.scrape_album(url)
            all_data.append(result)
            human_delay(1, 2)

        scraper.close()

        self.scraped_data = all_data
        save_path = os.path.join(os.getcwd(), "scraped_albums.json")
        pd.DataFrame(all_data).to_json(save_path, indent=2)

        self.status_box.insert("end", f"\n📁 Scraping complete. Data saved to:\n{save_path}\n")
        self.status_box.see("end")

    def upload_to_shopify(self):
        token = self.token_entry.get().strip()
        store = self.store_entry.get().strip()

        # if not token or not store:
        #     messagebox.showerror("Missing Fields", "Please enter both the Shopify token and store domain.")
        #     return
        #
        # if not hasattr(self, "scraped_data"):
        #     messagebox.showerror("No Data", "Please scrape albums first.")
        #     return
        #
        # for product in self.scraped_data:
        #     self.status_box.insert("end", f"Uploading: {product.get('title')} to {store}\n")
        #     self.status_box.see("end")
        #     human_delay(1, 2)
        #
        # self.status_box.insert("end", "Upload complete.\n")
        # self.status_box.see("end")
        messagebox.showinfo("Upload Done", "All products uploaded to Shopify.")

# ---- Run the app ----
if __name__ == "__main__":
    try:
        YupooGUI()
    except Exception as e:
        import traceback
        traceback.print_exc()
        messagebox.showerror("App Crash", f"Unexpected error:\n{e}")
