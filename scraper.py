##########UI
import customtkinter as ctk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox


###########################
#Functionality
##########################
from bs4 import BeautifulSoup
import time
import random
import re
import json
from selenium.common.exceptions import WebDriverException
import requests
import threading
import numpy as np
from curl_cffi import requests as curl_req
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium import webdriver
import os
import logging
import xml.etree.ElementTree as ET
import sys

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
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    


def resource_path(relative_path):
    """ Get absolute path to resource, compatible with PyInstaller .exe """
    try:
        # PyInstaller stores temp path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        # Normal dev mode
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


# ─────────────────────────── GraphQL templates ──────────────────────────
PRODUCT_CREATE_MUTATION = """
    mutation CreateProductWithNewMedia($product: ProductCreateInput!, $media: [CreateMediaInput!]) {
      productCreate(product: $product, media: $media) {
        product {
          id
          title
          media(first: 10) {
            nodes {
              alt
              mediaContentType
              preview {
                status
              }
            }
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """
PRODUCT_VARIANTS_BULK_CREATE_MUTATION = """
mutation ProductVariantsCreate($productId: ID!, $variants: [ProductVariantsBulkInput!]!, $strategy: ProductVariantsBulkCreateStrategy) {
  productVariantsBulkCreate(productId: $productId, variants: $variants, strategy:$strategy) {
    productVariants {
      id
      title
      selectedOptions {
        name
        value
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""

PUBLISH_MUTATION = """
mutation publishablePublish($id: ID!, $input: [PublicationInput!]!) {
  publishablePublish(id: $id, input: $input) {
    publishable {
      availablePublicationsCount {
        count
      }
      resourcePublicationsCount {
        count
      }
    }
    shop {
      publicationCount
    }
    userErrors {
      field
      message
    }
  }
}
"""

ALL_PRODUCTS_QUERY = """
{
  products(first: 250, after: AFTER_CURSOR) {
    edges {
      cursor
      node {
        id
        title
      }
    }
    pageInfo {
      hasNextPage
    }
  }
}
"""


ALL_IMAGES_QUERY = """
    query GetProductImages($productId: ID!, $cursor: String) {
      product(id: $productId) {
        media(first: 100, after: $cursor) {
          edges {
            node {
              id
              alt
            }
          }
          pageInfo {
            hasNextPage
            endCursor
          }
        }
      }
    }
    """

ALL_PUBLICATIONS_QUERY = """
query ($first: Int!, $after: String) {
  publications(first: $first, after: $after) {
    edges {
      cursor
      node {
        id
        name
      }
    }
    pageInfo {
      hasNextPage
    }
  }
}
"""

ALL_LOCATIONS_QUERY = """
query ($first: Int!, $after: String) {
  locations(first: $first, after: $after) {
    edges {
      cursor
      node {
        id
        name
        address {
          address1
          city
          country
        }
      }
    }
    pageInfo {
      hasNextPage
    }
  }
}
"""

# ------------------- Shopify Upload Class ------------------- #

class ShopifyUploader:
    def __init__(self, shop_domain: str, access_token: str, api_version="2024-07"):
        if not shop_domain.startswith("https://"):
            shop_domain = f"https://{shop_domain}"
        self.endpoint = f"{shop_domain}/admin/api/{api_version}/graphql.json"
        self.headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token,
        }

    # ────────────────────────────────────────────────────────────────
    #  helpers
    # ────────────────────────────────────────────────────────────────
    def _post(self, query, variables):
        r = requests.post(
            self.endpoint,
            json={"query": query, "variables": variables},
            headers=self.headers,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    # ────────────────────────────────────────────────────────────────
    #  media helpers
    # ────────────────────────────────────────────────────────────────
    def get_product_images(self, product_id):
        """Return a {alt_text: media_id} mapping."""
        media_alts = {}
        cursor = None

        while True:
            resp = self._post(
                ALL_IMAGES_QUERY, {"productId": product_id, "cursor": cursor}
            )

            media = resp.get("data", {}).get("product", {}).get("media", {})
            edges = media.get("edges", [])
            for edge in edges:
                node = edge["node"]
                if node.get("alt"):
                    media_alts[node["alt"]] = node["id"]

            page_info = media.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info["endCursor"] 

        return media_alts

    # ────────────────────────────────────────────────────────────────
    #  export catalogue
    # ────────────────────────────────────────────────────────────────
    def dump_all_products(self, out_file=None):
        if out_file is None:
            out_file = resource_path("Data/shopify_all_products.json")
        products = []
        cursor = None
        has_next_page = True

        while has_next_page:
            query = ALL_PRODUCTS_QUERY.replace("AFTER_CURSOR", f'"{cursor}"' if cursor else "null")
            
            response = requests.post(self.endpoint, json={"query": query}, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                if "data" in data and "products" in data["data"]:
                    for product in data["data"]["products"]["edges"]:
                        product = {"id": product["node"]["id"], "title": product["node"]["title"]}   
                        products.append(product)
                    
                    has_next_page = data["data"]["products"]["pageInfo"]["hasNextPage"]
                    if has_next_page:
                        cursor = data["data"]["products"]["edges"][-1]["cursor"]
                else:
                    print("No product data found in the response.")
                    break
            else:
                print(f"Error: {response.status_code}, {response.text}")
                break

        os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as fh:
            json.dump(products, fh, indent=2, ensure_ascii=False)
        print(products)
        return products

    # ────────────────────────────────────────────────────────────────
    #  publishing
    # ────────────────────────────────────────────────────────────────
    def publish_product(self, product_id, publication_ids):
        variables = {
            "id": product_id,
            "input": [{"publicationId": pid} for pid in publication_ids],
        }
        resp = self._post(PUBLISH_MUTATION, variables)

        errs = resp["data"]["publishablePublish"]["userErrors"]
        if errs:
            logging.error("Publish errors: %s", errs)
        else:
            logging.info(
                "Product %s published to %d publication(s)",
                product_id,
                len(publication_ids),
            )

    # ────────────────────────────────────────────────────────────────
    #  variants
    # ────────────────────────────────────────────────────────────────
    def create_variants(self, product_id, product):
        media_dict = self.get_product_images(product_id)
        media_id = media_dict.get("index_0")
        location_Ids = self.get_location_ids()
        inventoryQuantities = []
        for location_Id in location_Ids:
            lc = {"availableQuantity": 20, "locationId": location_Id}
            inventoryQuantities.append(lc)


        option_values = [{"name": product.get("size"), "optionName": "SIZE"}]

        variants = [
            {
                "inventoryPolicy": "DENY",
                "inventoryQuantities": inventoryQuantities,
                "mediaId": media_id,
                "optionValues": option_values,
                "taxable": True,
            }
        ]

        resp = self._post(
            PRODUCT_VARIANTS_BULK_CREATE_MUTATION,
            {
                "productId": product_id,
                "variants": variants,
                "strategy": "REMOVE_STANDALONE_VARIANT",
            },
        )

        errs = resp["data"]["productVariantsBulkCreate"]["userErrors"]
        if errs:
            logging.error("Variant creation errors: %s", errs)

    # ────────────────────────────────────────────────────────────────
    #  publications
    # ────────────────────────────────────────────────────────────────
    def get_publication_ids(self):
        ids = []
        cursor = None

        while True:
            resp = self._post(ALL_PUBLICATIONS_QUERY, {"first": 100, "after": cursor})
            pdata = resp["data"]["publications"]
            edges = pdata["edges"]

            for edge in edges:
                pub = edge["node"]
                ids.append(pub["id"])
                

            if not pdata["pageInfo"]["hasNextPage"]:
                break
            cursor = edges[-1]["cursor"]

        return ids
    
    # ────────────────────────────────────────────────────────────────
    #  Location Ids
    # ────────────────────────────────────────────────────────────────

    def get_location_ids(self):
        ids = []
        
        cursor = None

        while True:
            resp = self._post(ALL_LOCATIONS_QUERY, {"first": 100, "after": cursor})
            try:
                pdata = resp["data"]["locations"]
                edges = pdata["edges"]
            except (KeyError, TypeError):
                raise RuntimeError("Unexpected GraphQL payload:\n" + str(resp)) from None

            for edge in edges:
                node = edge["node"]
                ids.append(node["id"])
                

            if not pdata["pageInfo"]["hasNextPage"]:
                break
            cursor = edges[-1]["cursor"]

        logging.info("Locations: %s", ids)
        return ids
    
    # ────────────────────────────────────────────────────────────────
    #  Downloading Images
    # ────────────────────────────────────────────────────────────────

    def get_cookies_as_dict(self, driver):
        return {cookie['name']: cookie['value'] for cookie in driver.get_cookies()}

    def download_image_with_cookies(self, img_url, cookies, dest_path):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Referer": "https://yupoo.com/"
        }
        resp = curl_req.get(img_url, cookies=cookies, headers=headers, impersonate="chrome")
        if resp.status_code == 200:
            with open(dest_path, "wb") as f:
                f.write(resp.content)
            return True
        return False
    
    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        return webdriver.Chrome(service=Service(), options=chrome_options)

    def get_album_cookies(self, driver, album_url):
        driver.get(album_url)
        return self.get_cookies_as_dict(driver)

    # ────────────────────────────────────────────────────────────────
    #  full product upload
    # ────────────────────────────────────────────────────────────────

    def get_staged_upload(self, filename):
        mutation = """
        mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
        stagedUploadsCreate(input: $input) {
            stagedTargets {
            url
            resourceUrl
            parameters {
                name
                value
            }
            }
            userErrors {
            field
            message
            }
        }
        }
        """
        variables = {
            "input": [{
                "filename": filename,
                "mimeType": "image/jpeg",
                "httpMethod": "POST",
                "resource": "PRODUCT_IMAGE"
                
            }]
        }

        resp = requests.post(
            self.endpoint,
            headers=self.headers,
            json={"query": mutation, "variables": variables}
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"]["stagedUploadsCreate"]["stagedTargets"][0]
    
    

    def upload_file_to_target(self, file_path, staged_target):
        files = {}
        data = {param["name"]: param["value"] for param in staged_target["parameters"]}
        
        with open(file_path, "rb") as f:
            files["file"] = (os.path.basename(file_path), f, "image/jpeg")
            upload_resp = requests.post(staged_target["url"], data=data, files=files)

        # Accept both 204 (no content) and 201 (created with XML response)
        if upload_resp.status_code == 204:
            return staged_target["resourceUrl"]
        
        elif upload_resp.status_code == 201:
            try:
                # Parse XML to get <Location> tag value
                root = ET.fromstring(upload_resp.text)
                location = root.findtext("Location")
                if location:
                    return location
                else:
                    raise Exception("Missing <Location> tag in response")
            except Exception as e:
                raise Exception(f"Upload succeeded (201) but failed to parse XML: {e}")

        # All other cases are failures
        raise Exception(f"Upload failed: {upload_resp.status_code} - {upload_resp.text}")


    def _cleanup_images(self):
        images_dir = resource_path("Images")
        try:
            for filename in os.listdir(images_dir):
                if filename.lower().endswith(".jpg"):
                    file_path = os.path.join(images_dir, filename)
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        logging.warning(f"⚠️ Could not delete {file_path}: {e}")
        except Exception as e:
            logging.error(f"❌ Failed to access directory {images_dir}: {e}")

    def upload_product(self, product, publication_ids):
            option = {
                "name": "SIZE",
                "position": 1,
                "values": [{"name": product["size"]}],
            }
            product_input = {
                "handle": product["title"].lower().replace(" ", "-"),
                "title": product["title"],
                "tags": product["title"],
                "productOptions": [option],
                "status": "ACTIVE",
            }

            driver = self.setup_driver()
            try:
                cookies = self.get_album_cookies(driver, product["url"])

                media_input = []
                for idx, img_url in enumerate(product["image_urls"]):
                    try:
                        fname = f"{product['title'].lower().replace(' ', '_').replace('/', '')}_index_{idx}.jpg"

                        local_path = os.path.join(resource_path("Images"), fname)
                        full_url = img_url

                        # Download image locally first
                        success = self.download_image_with_cookies(full_url, cookies, local_path)
                        if not success:
                            raise Exception("Image download failed")

                        # Step 1: Request upload target from Shopify
                        staged = self.get_staged_upload(fname)

                        # Step 2: Upload to Shopify CDN
                        cdn_url = self.upload_file_to_target(local_path, staged)

                        # Step 3: Add to media_input
                        media_input.append({
                            "mediaContentType": "IMAGE",
                            "originalSource": cdn_url,
                            "alt": f"index_{idx}",
                        })
                    except Exception as e:
                        logging.warning(f"⚠️ Failed processing image: {img_url} – {e}")

            finally:
                driver.quit()

            # Step 4: Create product
            resp = self._post(PRODUCT_CREATE_MUTATION, {
                "product": product_input,
                "media": media_input
            })

            payload = resp["data"]["productCreate"]
            if payload["userErrors"]:
                logging.error("ProductCreate errors: %s", payload["userErrors"])
                return

            product_id = payload["product"]["id"]
            logging.info("✅ Created product %s – %s", product_id, product["title"])

            self.publish_product(product_id, publication_ids)
            self.create_variants(product_id, product)
            self._cleanup_images()


# ------------------- Scraper Class ------------------- #
class YupooScraper:
    def __init__(self, debug=False):
        self.debug = debug
        logging.info("Initialized curl_cffi.")
        self.headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://minkang.x.yupoo.com/",
        }

    def scrape_album(self, url: str) -> dict:
        logging.info(f"Scraping album: {url}")
        data = {
            "url": url,
            "title": None,
            "image_urls": [],
            "size": ""
        }

        try:
            response = curl_req.get(
            url,
            headers=self.headers,
            impersonate="chrome120",
            timeout=30,
                )

            # Get final HTML and parse
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract album title from page
            title_tag = soup.find("span", class_="showalbumheader__gallerytitle")
            if title_tag:
                raw_title = title_tag.get_text(strip=True)
            else:
                raw_title = soup.title.string.strip() if soup.title else "Untitled"


            # Extract size range using flexible regex (handles S-XXL, S to XXL, S ~ XXL, etc.)

            size_match = re.search(r"\bS-(\S+)", raw_title) 
            
            if size_match:
                size_clean = size_match.group(1)
                data['size'] = size_clean
            else:
                data['size'] = ""

            data['title'] = raw_title

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

            logging.info(f"Scraped: {raw_title} | {len(data['image_urls'])} images | Size: {data['size']}")

            if self.debug:
                self._save_debug_screenshot(raw_title)

        except WebDriverException as e:
            logging.error(f"curl_cffi error: {e}")
        except Exception as e:
            logging.error(f"Error scraping {url}: {e}")

        return data

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

import tkinter as tk


class YupooGUI:
    # ──────────────────────────────────────────────────────────────────── #
    # 1.  Constructor & persistent state
    # ──────────────────────────────────────────────────────────────────── #
    def __init__(self):
        ctk.set_default_color_theme("green")

        self.root = ctk.CTk()
        self.root.title("Yupoo → Shopify Scraper / Uploader")
        self.root.geometry("720x600")

        # persistent data
        self.csv_urls: list[str] = []        
        self.scraped_data: list[dict] = []    

        # control flags / thread helpers
        self.scrape_stop = threading.Event()
        self.upload_stop = threading.Event()

        self._build_ui()
        self.root.mainloop()

    # ──────────────────────────────────────────────────────────────────── #
    # 2.  UI construction
    # ──────────────────────────────────────────────────────────────────── #
    def _build_ui(self):
        # ── title
        ctk.CTkLabel(
            self.root,
            text="Yupoo Scraper  ➜  Shopify Uploader",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=10)

        # ── manual URL textbox
        self.url_box = ctk.CTkTextbox(
            self.root, height=120, width=600, corner_radius=6, border_width=1
        )
        self.url_box.pack(pady=(5, 10))

        self._url_placeholder = (
            "📝 Paste one Yupoo album URL per line, e.g.:\n"
            "https://example.yupoo.com/albums/12345678\n"
            "https://anotheruser.yupoo.com/albums/98765432"
        )
        self.url_placeholder_active = True
        self.url_box.insert("1.0", self._url_placeholder)
        self.url_box.bind("<FocusIn>", self._clear_placeholder)
        self.url_box.bind("<FocusOut>", self._restore_placeholder)

        # ── CSV controls
        btn_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        btn_frame.pack(pady=5)

        self.load_csv_btn = ctk.CTkButton(
            btn_frame, text="📁 Load URLs from CSV", command=self.load_csv
        )
        self.load_csv_btn.pack(side="left", padx=5)

        self.discard_csv_btn = ctk.CTkButton(
            btn_frame,
            text="❌ Discard CSV",
            command=self.discard_csv,
            fg_color="#A80000",
            hover_color="#800000",
        )
        self.discard_csv_btn.pack(side="left", padx=5)
        self.discard_csv_btn.pack_forget()  # hidden until CSV is loaded

        # ── scrape button
        self.scrape_btn = ctk.CTkButton(
            self.root,
            text="🕷 Scrape Albums",
            command=self.start_scrape,
            fg_color="#4CAF50",
            hover_color="#45A049",
        )
        self.scrape_btn.pack(pady=10)

        # ── Shopify credentials
        ctk.CTkLabel(self.root, text="Shopify Access Token:").pack()
        self.token_entry = ctk.CTkEntry(self.root, width=400)
        self.token_entry.pack(pady=(0, 5))

        ctk.CTkLabel(
            self.root, text="Shopify Store Domain (e.g. mystore.myshopify.com):"
        ).pack()
        self.store_entry = ctk.CTkEntry(self.root, width=400)
        self.store_entry.pack(pady=(0, 10))

        self.upload_btn = ctk.CTkButton(
            self.root, text="🚀 Upload to Shopify", command=self.start_upload
        )
        self.upload_btn.pack(pady=5)

        # ── status console
        self.status_box = ctk.CTkTextbox(self.root, height=180, width=680)
        self.status_box.pack(pady=10)

    # ──────────────────────────────────────────────────────────────────── #
    # 3.  Placeholder helpers
    # ──────────────────────────────────────────────────────────────────── #
    def _clear_placeholder(self, *_):
        if self.url_placeholder_active:
            self.url_box.delete("1.0", "end")
            self.url_placeholder_active = False

    def _restore_placeholder(self, *_):
        if not self.url_box.get("1.0", "end-1c").strip():
            self.url_box.insert("1.0", self._url_placeholder)
            self.url_placeholder_active = True

    # ──────────────────────────────────────────────────────────────────── #
    # 4.  CSV load / discard
    # ──────────────────────────────────────────────────────────────────── #
    def load_csv(self):
        try:
            path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
            if not path:
                return

            # Read the header row and check for 'url' column
            with open(path, 'r', encoding='utf-8') as f:
                header = f.readline().strip().lower().split(',')
                if "url" not in header:
                    messagebox.showerror("Invalid CSV", "CSV must contain a 'url' column.")
                    return
                url_idx = header.index("url")

            # Load only the URL column using NumPy
            data = np.genfromtxt(path, delimiter=',', dtype=str, skip_header=1)
            if data.ndim == 1:
                urls = [data[url_idx]] if data[url_idx] else []
            else:
                urls = [row[url_idx] for row in data if row[url_idx]]

            self.csv_urls = urls
            self.status_box.insert("end", f"✅ Loaded {len(self.csv_urls)} URLs from CSV\n")
            self.status_box.see("end")
            self.discard_csv_btn.pack(side="left", padx=5)  # show the X button

        except Exception as exc:
            messagebox.showerror("Error", str(exc))
    def discard_csv(self):
        self.csv_urls.clear()
        self.discard_csv_btn.pack_forget()
        self.status_box.insert("end", "🗑️ CSV URLs discarded.\n")
        self.status_box.see("end")

    # ──────────────────────────────────────────────────────────────────── #
    # 5.  Common UI state helpers
    # ──────────────────────────────────────────────────────────────────── #
    def _disable_inputs(self):
        widgets = (
            self.load_csv_btn,
            self.discard_csv_btn,
            self.url_box,
            self.token_entry,
            self.store_entry,
            self.upload_btn,
        )
        for w in widgets:
            w.configure(state=tk.DISABLED)

    def _enable_inputs(self):
        widgets = (
            self.load_csv_btn,
            self.url_box,
            self.token_entry,
            self.store_entry,
            self.upload_btn,
        )
        for w in widgets:
            w.configure(state=tk.NORMAL)
        # show discard button only if CSV present
        if self.csv_urls:
            self.discard_csv_btn.configure(state=tk.NORMAL)
            self.discard_csv_btn.pack(side="left", padx=5)

    # ──────────────────────────────────────────────────────────────────── #
    # 6.  Scraping logic
    # ──────────────────────────────────────────────────────────────────── #
    def start_scrape(self):
        # switch button to STOP + disable others
        self.scrape_btn.configure(
            text="⏹ Stop", command=self.stop_scrape, fg_color="#D9534F", hover_color="#C9302C"
        )
        self._disable_inputs()
        self.scrape_stop.clear()

        threading.Thread(target=self._scrape_worker, daemon=True).start()

    def stop_scrape(self):
        self.scrape_stop.set()
        self._write_status("🛑 Stopping scrape …\n")

    def _scrape_worker(self):
        # gather manual URLs
        manual_urls = []
        if not self.url_placeholder_active:
            manual_urls = [
                u.strip()
                for u in self.url_box.get("1.0", "end").splitlines()
                if u.strip().startswith("http")
            ]

        combined = manual_urls + self.csv_urls
        urls = list(set(combined))  # dedup

        if not urls:
            self._thread_safe(lambda: messagebox.showerror("Error", "No URLs to scrape."))
            self._thread_safe(self._reset_scrape_button)
            return

        self._write_status(
            f"Total URLs input: {len(combined)}\n"
            f"Duplicates removed: {len(combined) - len(urls)}\n"
            f"✅ Unique URLs to scrape: {len(urls)}\n\n"
        )

        scraper = YupooScraper(debug=False)
        data = []

        for url in urls:
            
            if self.scrape_stop.is_set():
                break
            self._write_status(f"🔍 Scraping: {url}\n")
            data.append(scraper.scrape_album(url))
            human_delay(2, 4)

        self.scraped_data = data

        if data:

            out_path = os.path.join(os.getcwd(), "Data/scraped_albums.json")
            with open(out_path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=2, ensure_ascii=False)
            self._write_status(f"\n📁 Scraping complete.")
        else:
            self._write_status("\n⚠️ No data scraped.\n")

        self._thread_safe(self._reset_scrape_button)

    def _reset_scrape_button(self):
        self.scrape_btn.configure(
            text="🕷 Scrape Albums",
            command=self.start_scrape,
            fg_color="#4CAF50",
            hover_color="#45A049",
        )
        self._enable_inputs()

    # ──────────────────────────────────────────────────────────────────── #
    # 7.  Upload logic
    # ──────────────────────────────────────────────────────────────────── #
    def start_upload(self):
        if not self.scraped_data:
            messagebox.showerror("No Data", "Please scrape albums first.")
            return

        # build (or reuse) the uploader once per GUI session ➋
        token = self.token_entry.get().strip()
        store = self.store_entry.get().strip()
        if not token or not store:
            messagebox.showerror("Missing Fields", "Enter both token and store domain.")
            return
        self.uploader = ShopifyUploader(store, token, api_version="2025-07")

        # button ➜ STOP, disable widgets
        self.upload_btn.configure(text="⏹ Stop", command=self.stop_upload,
                                  fg_color="#D9534F", hover_color="#C9302C")
        self._disable_inputs()
        self.scrape_btn.configure(state=tk.DISABLED)
        self.upload_stop.clear()

        threading.Thread(target=self._upload_worker, daemon=True).start()

    def stop_upload(self):
        self.upload_stop.set()
        self._write_status("🛑 Stopping upload …\n")

    def _upload_worker(self):
        try:
            #  dump once, keep JSON in memory
            self._write_status("📦 Fetching existing Shopify catalog…\n")
    
            all_products = self.uploader.dump_all_products()  # add "return_list" option in class
            
            products_seen = {p["title"].strip(): p for p in all_products}
            

            #  get publication IDs once
            pub_ids = self.uploader.get_publication_ids()
            

        except Exception as exc:                  
            self._thread_safe(lambda: messagebox.showerror("Shopify error", str(exc)))
            self._thread_safe(self._reset_upload_button)
            return

        for scraped in self.scraped_data:
            human_delay(2, 4)
            if self.upload_stop.is_set():
                break

            title = scraped.get("title", "Unnamed product")
            self._thread_safe(lambda t=title: self._write_status(f"⬆️  {t}\n"))

            if title in products_seen:
                self._thread_safe(lambda: self._write_status("   ‑ already in store, skipped\n"))
                continue

            try:
                self.uploader.upload_product(scraped, pub_ids)   # ➎
            except Exception as exc:
                self._thread_safe(lambda e=exc: self._write_status(f"   ‑ error: {e}\n"))
            else:
                self._thread_safe(lambda: self._write_status("   ✓ uploaded\n"))

        # final UI reset
        self._thread_safe(
            lambda: self._write_status("\n✅ Upload complete.\n")
                     if not self.upload_stop.is_set()
                     else self._write_status("\n⚠️ Upload cancelled.\n")
        )
        self._thread_safe(self._reset_upload_button)

    def _reset_upload_button(self):
        self.upload_btn.configure(
            text="🚀 Upload to Shopify",
            command=self.start_upload,
            fg_color="#3B8ED0",
            hover_color="#357ABD",
        )
        self.scrape_btn.configure(state=tk.NORMAL)
        self._enable_inputs()

    # ──────────────────────────────────────────────────────────────────── #
    # 8.  Utilities
    # ──────────────────────────────────────────────────────────────────── #
    def _write_status(self, msg: str):
        self.status_box.insert("end", msg)
        self.status_box.see("end")

    def _thread_safe(self, fn):
        self.root.after(0, fn)


# ────────────────────────────────
# Main GUI bootstrap
# ────────────────────────────────
if __name__ == "__main__":
    try:
        app = YupooGUI()

    except Exception as exc:
        import traceback
        traceback.print_exc()
        messagebox.showerror("App Crash", f"Unexpected error:\n{exc}")

