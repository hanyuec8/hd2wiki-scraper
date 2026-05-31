import os
import sys
import re
import time
import urllib.request
import urllib.error
import io
import random
import argparse
from multiprocessing import Pool
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==============================================================================
# ─── 공통 헬퍼 및 드라이버 생성 ────────────────────────────────────────────────
# ==============================================================================

def _make_driver(headless=True):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('--headless')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            })
        '''
    })
    return driver

def thumb_to_full(src):
    """
    wiki.gg 썸네일 URL → 원본 이미지 URL 변환
    """
    if not src:
        return None
    if "/thumb/" in src:
        parts = src.split("/")
        parts.pop()               # 해상도 제거 (예: 120px-File.png)
        parts.remove("thumb")     # "/thumb/" 경로 부분 제거
        src = "/".join(parts)
    if src.startswith("//"):
        src = "https:" + src
    return src

# ==============================================================================
# ─── 개별 자산 다운로드 테스크 (멀티프로세싱 호환을 위해 전역 레벨 선언) ────────────────
# ==============================================================================

# 1. 부스터 (Booster) 다운로드 Task
def download_booster_task(args):
    cat, name, cat_dir, record_file, cookie_str, img_urls = args
    safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
        'Referer': 'https://helldivers.wiki.gg/'
    }
    if cookie_str:
        headers['Cookie'] = cookie_str
        
    error_msgs = []
    success = False
    urls_to_try = [img_urls] if isinstance(img_urls, str) else img_urls
    
    for img_url in urls_to_try:
        if not img_url:
            continue
        try:
            time.sleep(random.uniform(0.5, 1.5))
            req = urllib.request.Request(img_url, headers=headers)
            with urllib.request.urlopen(req) as response:
                img_data = response.read()
                content_type = response.headers.get('Content-Type', '')
            
            is_svg = ".svg" in img_url.lower() or "image/svg+xml" in content_type.lower()
            
            if is_svg:
                temp_svg_path = os.path.join(cat_dir, f"{safe_name}_temp.svg")
                with open(temp_svg_path, 'wb') as out_file:
                    out_file.write(img_data)
                
                try:
                    from svglib.svglib import svg2rlg
                    from reportlab.graphics import renderPM
                    
                    drawing = svg2rlg(temp_svg_path)
                    png_path = os.path.join(cat_dir, f"{safe_name}_temp.png")
                    renderPM.drawToFile(drawing, png_path, fmt="PNG")
                    
                    webp_path = os.path.join(cat_dir, f"{safe_name}.webp")
                    image = Image.open(png_path)
                    image.save(webp_path, "WEBP")
                    image.close()
                finally:
                    if os.path.exists(temp_svg_path):
                        try: os.remove(temp_svg_path)
                        except: pass
                    if os.path.exists(png_path):
                        try: os.remove(png_path)
                        except: pass
            else:
                png_path = os.path.join(cat_dir, f"{safe_name}.png")
                webp_path = os.path.join(cat_dir, f"{safe_name}.webp")
                with open(png_path, 'wb') as out_file:
                    out_file.write(img_data)
                    
                image = Image.open(png_path)
                image.save(webp_path, "WEBP")
                image.close()
                if os.path.exists(png_path):
                    os.remove(png_path)
            
            success = True
            break
        except urllib.error.HTTPError as e:
            error_msgs.append(f"HTTP Error {e.code}: {e.reason} ({img_url})")
        except Exception as e:
            error_msgs.append(str(e))
            
    if not success:
        return False, name, cat, safe_name, " | ".join(error_msgs)
    return True, name, cat, safe_name, None


# 2. 망토 (Cape) 다운로드 Task
def download_cape_task(args):
    cat, name, cat_dir, record_file, cookie_str, img_urls = args
    safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")
    webp_path = os.path.join(cat_dir, f"{safe_name}.webp")
    png_path = os.path.join(cat_dir, f"{safe_name}.png")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
        'Referer': 'https://helldivers.wiki.gg/'
    }
    if cookie_str:
        headers['Cookie'] = cookie_str
        
    error_msgs = []
    success = False
    urls_to_try = [img_urls] if isinstance(img_urls, str) else img_urls
    
    for img_url in urls_to_try:
        if not img_url:
            continue
        try:
            time.sleep(random.uniform(0.5, 1.5))
            req = urllib.request.Request(img_url, headers=headers)
            with urllib.request.urlopen(req) as response:
                img_data = response.read()
                
            with open(png_path, 'wb') as out_file:
                out_file.write(img_data)
                
            image = Image.open(png_path)
            image.save(webp_path, "WEBP")
            image.close()
            if os.path.exists(png_path):
                os.remove(png_path)
            
            success = True
            break
        except urllib.error.HTTPError as e:
            error_msgs.append(f"HTTP Error {e.code}: {e.reason} ({img_url})")
        except Exception as e:
            error_msgs.append(str(e))
            
    if not success:
        if os.path.exists(png_path):
            try: os.remove(png_path)
            except: pass
        return False, name, cat, safe_name, " | ".join(error_msgs)
    return True, name, cat, safe_name, None


# 3. 헬멧 (Helmet) 다운로드 Task
def download_helmet_task(args):
    return download_cape_task(args) # 로직이 완전히 동일하므로 재사용


# 4. 방어구 (Armor) 다운로드 Task
def download_armor_task(args):
    cat, name, cat_dir, record_file, cookie_str, img_url = args
    safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")
    webp_path = os.path.join(cat_dir, f"{safe_name}.webp")
    png_path = os.path.join(cat_dir, f"{safe_name}.png")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
        'Referer': 'https://helldivers.wiki.gg/'
    }
    if cookie_str:
        headers['Cookie'] = cookie_str
        
    try:
        time.sleep(random.uniform(0.5, 1.5))
        req = urllib.request.Request(img_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            img_data = response.read()
            
        with open(png_path, 'wb') as out_file:
            out_file.write(img_data)
            
        image = Image.open(png_path)
        image.save(webp_path, "WEBP")
        image.close()
        if os.path.exists(png_path):
            os.remove(png_path)
        return True, name, cat, safe_name, None
    except urllib.error.HTTPError as e:
        return False, name, cat, safe_name, f"HTTP Error {e.code}: {e.reason} ({img_url})"
    except Exception as e:
        if os.path.exists(png_path):
            try: os.remove(png_path)
            except: pass
        return False, name, cat, safe_name, str(e)


# 5. 스트라타젬 (Stratagem) 다운로드 Task
def download_stratagem_task(args):
    return download_booster_task(args) # 로직이 완전히 동일하므로 재사용


# 6. 무기 (Weapon) 다운로드 Task 및 스레드식 개별 URL 패치 헬퍼
def download_weapon_task(args):
    cat, w_class, name, cat_dir, record_file, cookie_str, img_url = args
    safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")
    
    W_CLASS_MAP = {
        "Assault Rifle": "돌격 소총", "Assault_Rifle": "돌격 소총",
        "Energy-Based": "에너지계", "Explosive": "폭발성",
        "Marksman Rifle": "지정사수소총", "Marksman_Rifle": "지정사수소총",
        "Shotgun": "산탄총", "Special": "특수",
        "Submachine Gun": "기관단총", "Submachine_Gun": "기관단총",
        "Melee": "근접", "Pistol": "권총", "Standard": "표준"
    }
    
    mapped_w_class = W_CLASS_MAP.get(w_class, w_class)
    safe_w_class = mapped_w_class.replace("/", "_")
    target_dir = os.path.join(cat_dir, safe_w_class)
    os.makedirs(target_dir, exist_ok=True)

    webp_path = os.path.join(target_dir, f"{safe_name}.webp")
    png_path  = os.path.join(target_dir, f"{safe_name}.png")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
        'Referer': 'https://helldivers.wiki.gg/'
    }
    if cookie_str:
        headers['Cookie'] = cookie_str

    try:
        time.sleep(random.uniform(0.3, 1.0))
        req = urllib.request.Request(img_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            img_data = response.read()

        with open(png_path, 'wb') as f:
            f.write(img_data)

        # 50% 리사이즈 후 1920x1080 캔버스에 중앙 배치
        img = Image.open(png_path).convert("RGBA")
        new_w = max(1, img.width  // 2)
        new_h = max(1, img.height // 2)
        img_resized = img.resize((new_w, new_h), Image.LANCZOS)

        canvas = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        paste_x = (1920 - new_w) // 2
        paste_y = (1080 - new_h) // 2
        canvas.paste(img_resized, (paste_x, paste_y), img_resized)
        canvas.save(webp_path, "WEBP")

        if os.path.exists(png_path):
            os.remove(png_path)
        return True, name, cat, w_class, safe_name, target_dir, None
    except urllib.error.HTTPError as e:
        err = f"HTTP Error {e.code}: {e.reason} ({img_url})"
    except Exception as e:
        err = str(e)

    if os.path.exists(png_path):
        try: os.remove(png_path)
        except: pass
    return False, name, cat, w_class, safe_name, target_dir, err

def _fetch_weapon_url(args):
    name, cat_key, headless = args
    driver = None
    try:
        driver = _make_driver(headless=headless)
        url_name = name.replace(" ", "_")
        cat_cap  = cat_key.capitalize()
        file_name = f"{url_name}_{cat_cap}_Render.png"
        file_page = f"https://helldivers.wiki.gg/wiki/File:{file_name}"

        driver.get(file_page)
        time.sleep(1.5)

        for sel in [".fullImageLink a", "#file a", "a.internal", "div.fullMedia a"]:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                href = el.get_attribute("href") or ""
                if href and ("upload" in href or ".png" in href.lower()):
                    return name, href

        for img in driver.find_elements(By.CSS_SELECTOR, "img"):
            src = img.get_attribute("src") or ""
            if "upload" in src and "_Render" in src:
                return name, thumb_to_full(src)
        return name, None
    except Exception:
        return name, None
    finally:
        if driver:
            try: driver.quit()
            except: pass

# ==============================================================================
# ─── 각 자산별 메인 수집 함수 정의 ─────────────────────────────────────────────
# ==============================================================================

# 1. 부스터 (Booster) 수집
def scrape_booster_images(output_dir=None, record_file=None, headless=True, workers=4):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = output_dir if output_dir else script_dir
    os.makedirs(base_dir, exist_ok=True)
    if not record_file:
        record_file = os.path.join(base_dir, "downloaded_booster.txt")
    else:
        record_file = os.path.abspath(record_file)
        
    downloaded_booster = set()
    if os.path.exists(record_file):
        with open(record_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    downloaded_booster.add(line.strip())
                    
    print(f"이전에 저장된 부스터 정보: {len(downloaded_booster)}개")

    driver = _make_driver(headless=headless)
    cookie_str = ""
    target_infos = [("Booster", "https://helldivers.wiki.gg/wiki/Boosters", 0)]
    booster_categories = {"Booster": []}
    booster_urls = {}
    
    try:
        for cat_name, url, table_index in target_infos:
            print(f" => 위키 페이지({cat_name}) 표 탐색 로딩 중...")
            driver.get(url)
            
            try:
                WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.wikitable")))
            except:
                print(f"   ({cat_name} 테이블을 찾을 수 없거나 타임아웃 되었습니다.)")
                continue
                
            tables = driver.find_elements(By.CSS_SELECTOR, "table.wikitable")
            if len(tables) > table_index:
                rows = tables[table_index].find_elements(By.TAG_NAME, "tr")
                for row in rows:
                    if row.find_elements(By.TAG_NAME, "th"):
                         continue
                    tds = row.find_elements(By.TAG_NAME, "td")
                    if len(tds) >= 2:
                        links = tds[1].find_elements(By.TAG_NAME, "a")
                        if links:
                            name = links[0].text.strip()
                            if name and name not in booster_categories[cat_name]:
                                booster_categories[cat_name].append(name)
                                try:
                                    img_tag = tds[0].find_element(By.TAG_NAME, "img")
                                    thumb_src = img_tag.get_attribute("src")
                                    booster_urls[name] = thumb_to_full(thumb_src)
                                except:
                                    url_name = name.replace(" ", "_").replace("\"", "%22")
                                    booster_urls[name] = [f"https://helldivers.wiki.gg/wiki/Special:FilePath/{url_name}_Booster_Icon.svg"]
                                
        total_found = sum(len(lst) for lst in booster_categories.values())
        print(f"위키에서 총 {total_found}개의 부스터 이름을 성공적으로 찾았습니다.")
        cookies = driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    finally:
        driver.quit()
        
    print("\n=== 멀티프로세싱 다운로드 시작 ===")
    tasks = []
    cat_dir = os.path.join(base_dir, "부스터")
    os.makedirs(cat_dir, exist_ok=True)
    
    for cat, names in booster_categories.items():
        for name in names:
            if name in downloaded_booster:
                print(f" => [패스] '{name}' 은(는) 이미 다운로드된 기록이 있습니다.")
                continue
            img_urls = booster_urls.get(name)
            tasks.append((cat, name, cat_dir, record_file, cookie_str, img_urls))

    if tasks:
        pool_size = min(os.cpu_count() or 4, workers, len(tasks))
        print(f" => 병렬 다운로드 시작 (프로세스 수: {pool_size})")
        with Pool(processes=pool_size) as pool:
            results = pool.map(download_booster_task, tasks)
        for success, name, cat, safe_name, error_msg in results:
            if success:
                print(f"   => 성공! 사진 다운로드 완료 (부스터/{safe_name})")
                with open(record_file, "a", encoding="utf-8") as f:
                    f.write(f"{name}\n")
                downloaded_booster.add(name)
            else:
                print(f"   => 실패! [{name}] 다운로드 중 에러가 발생했습니다: {error_msg}")
    else:
        print("다운로드할 새로운 이미지가 없습니다.")


# 2. 망토 (Cape) 수집
def scrape_cape_images(output_dir=None, record_file=None, headless=True, workers=4):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = output_dir if output_dir else script_dir
    os.makedirs(base_dir, exist_ok=True)
    if not record_file:
        record_file = os.path.join(base_dir, "downloaded_cape.txt")
    else:
        record_file = os.path.abspath(record_file)
        
    downloaded_cape = set()
    if os.path.exists(record_file):
        with open(record_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    downloaded_cape.add(line.strip())
                    
    print(f"이전에 저장된 망토 정보: {len(downloaded_cape)}개")

    driver = _make_driver(headless=headless)
    cookie_str = ""
    target_infos = [("Cape", "https://helldivers.wiki.gg/wiki/Armor#Cape-0", 4)]
    cape_categories = {"Cape": []}
    cape_urls = {}
    
    try:
        for cat_name, url, table_index in target_infos:
            print(f" => 위키 페이지({cat_name}) 표 탐색 로딩 중...")
            driver.get(url)
            
            try:
                WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.wikitable")))
            except:
                print(f"   ({cat_name} 테이블을 찾을 수 없거나 타임아웃 되었습니다.)")
                continue
                
            tables = driver.find_elements(By.CSS_SELECTOR, "table.wikitable")
            if len(tables) > table_index:
                rows = tables[table_index].find_elements(By.TAG_NAME, "tr")
                for row in rows:
                    if row.find_elements(By.TAG_NAME, "th"):
                        continue
                    tds = row.find_elements(By.TAG_NAME, "td")
                    if len(tds) >= 2:
                        links = tds[1].find_elements(By.TAG_NAME, "a")
                        if links:
                            name = links[0].text.strip()
                            if name and name not in cape_categories[cat_name]:
                                cape_categories[cat_name].append(name)
                                try:
                                    img_tag = tds[0].find_element(By.TAG_NAME, "img")
                                    thumb_src = img_tag.get_attribute("src")
                                    cape_urls[name] = thumb_to_full(thumb_src)
                                except:
                                    url_name = name.replace(" ", "_").replace("\"", "%22")
                                    cape_urls[name] = [f"https://helldivers.wiki.gg/wiki/Special:FilePath/{url_name}_Cape_Render.png"]
                                
        total_found = sum(len(lst) for lst in cape_categories.values())
        print(f"위키에서 총 {total_found}개의 망토 이름을 성공적으로 찾았습니다.")
        cookies = driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    finally:
        driver.quit()
        
    print("\n=== 멀티프로세싱 다운로드 및 WebP 변환 시작 ===")
    tasks = []
    cat_dir = os.path.join(base_dir, "망토")
    os.makedirs(cat_dir, exist_ok=True)
    
    for cat, names in cape_categories.items():
        for name in names:
            if name in downloaded_cape:
                print(f" => [패스] '{name}' 은(는) 이미 다운로드된 기록이 있습니다.")
                continue
            img_urls = cape_urls.get(name)
            tasks.append((cat, name, cat_dir, record_file, cookie_str, img_urls))

    if tasks:
        pool_size = min(os.cpu_count() or 4, workers, len(tasks))
        print(f" => 병렬 다운로드 시작 (프로세스 수: {pool_size})")
        with Pool(processes=pool_size) as pool:
            results = pool.map(download_cape_task, tasks)
        for success, name, cat, safe_name, error_msg in results:
            if success:
                print(f"   => 성공! 사진 다운로드 및 WebP 변환 완료 (망토/{safe_name}.webp)")
                with open(record_file, "a", encoding="utf-8") as f:
                    f.write(f"{name}\n")
                downloaded_cape.add(name)
            else:
                print(f"   => 실패! [{name}] 다운로드 중 에러가 발생했습니다: {error_msg}")
    else:
        print("다운로드할 새로운 이미지가 없습니다.")


# 3. 헬멧 (Helmet) 수집
def scrape_helmet_images(output_dir=None, record_file=None, headless=True, workers=4):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = output_dir if output_dir else script_dir
    os.makedirs(base_dir, exist_ok=True)
    if not record_file:
        record_file = os.path.join(base_dir, "downloaded_armors.txt")
    else:
        record_file = os.path.abspath(record_file)
        
    downloaded_armors = set()
    if os.path.exists(record_file):
        with open(record_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    downloaded_armors.add(line.strip())
                    
    print(f"이전에 저장된 헬멧 정보: {len(downloaded_armors)}개")

    driver = _make_driver(headless=headless)
    cookie_str = ""
    target_infos = [("Helmet", "https://helldivers.wiki.gg/wiki/Armor#Helmet-0", 3)]
    armor_categories = {"Helmet": []}
    armor_urls = {}
    
    try:
        for cat_name, url, table_index in target_infos:
            print(f" => 위키 페이지({cat_name}) 표 탐색 로딩 중...")
            driver.get(url)
            
            try:
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.wikitable")))
            except:
                print(f"   ({cat_name} 테이블을 찾을 수 없거나 타임아웃 되었습니다.)")
                continue
                
            tables = driver.find_elements(By.CSS_SELECTOR, "table.wikitable")
            if len(tables) > table_index:
                rows = tables[table_index].find_elements(By.TAG_NAME, "tr")
                for row in rows:
                    if row.find_elements(By.TAG_NAME, "th"):
                        continue
                    tds = row.find_elements(By.TAG_NAME, "td")
                    if len(tds) >= 2:
                        links = tds[1].find_elements(By.TAG_NAME, "a")
                        if links:
                            name = links[0].text.strip()
                            if name and name not in armor_categories[cat_name]:
                                armor_categories[cat_name].append(name)
                                try:
                                    img_tag = tds[0].find_element(By.TAG_NAME, "img")
                                    thumb_src = img_tag.get_attribute("src")
                                    armor_urls[name] = thumb_to_full(thumb_src)
                                except:
                                    url_name = name.replace(" ", "_").replace("\"", "%22")
                                    armor_urls[name] = [
                                        f"https://helldivers.wiki.gg/wiki/Special:FilePath/{url_name}_Helmet_Render.png",
                                        f"https://helldivers.wiki.gg/wiki/Special:FilePath/{url_name}_v1_Helmet_Render.png"
                                    ]
                                
        total_found = sum(len(lst) for lst in armor_categories.values())
        print(f"위키에서 총 {total_found}개의 헬멧 이름을 성공적으로 찾았습니다.")
        cookies = driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    finally:
        driver.quit()
 
    print("\n=== 멀티프로세싱 다운로드 및 WebP 변환 시작 ===")
    tasks = []
    cat_dir = os.path.join(base_dir, "헬멧")
    os.makedirs(cat_dir, exist_ok=True)
    
    for cat, names in armor_categories.items():
        for name in names:
            if name in downloaded_armors:
                print(f" => [패스] '{name}' 은(는) 이미 다운로드된 기록이 있습니다.")
                continue
            img_urls = armor_urls.get(name)
            tasks.append((cat, name, cat_dir, record_file, cookie_str, img_urls))
 
    if tasks:
        pool_size = min(os.cpu_count() or 4, workers, len(tasks))
        print(f" => 병렬 다운로드 시작 (프로세스 수: {pool_size})")
        with Pool(processes=pool_size) as pool:
            results = pool.map(download_helmet_task, tasks)
        for success, name, cat, safe_name, error_msg in results:
            if success:
                print(f"   => 성공! 사진 다운로드 및 WebP 변환 완료 (헬멧/{safe_name}.webp)")
                with open(record_file, "a", encoding="utf-8") as f:
                    f.write(f"{name}\n")
                downloaded_armors.add(name)
            else:
                print(f"   => 실패! [{name}] 다운로드 중 에러가 발생했습니다: {error_msg}")
    else:
        print("다운로드할 새로운 이미지가 없습니다.")


# 4. 방어구 (Armor) 수집
def scrape_armor_images(output_dir=None, record_file=None, headless=True, workers=4):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = output_dir if output_dir else script_dir
    os.makedirs(base_dir, exist_ok=True)
    if not record_file:
        record_file = os.path.join(base_dir, "downloaded_armors.txt")
    else:
        record_file = os.path.abspath(record_file)
        
    downloaded_armors = set()
    if os.path.exists(record_file):
        with open(record_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    downloaded_armors.add(line.strip())
                    
    print(f"이전에 저장된 갑옷 정보: {len(downloaded_armors)}개")

    driver = _make_driver(headless=headless)
    cookie_str = ""
    target_infos = [
        ("Light", "https://helldivers.wiki.gg/wiki/Armor#Light-0", 0),
        ("Medium", "https://helldivers.wiki.gg/wiki/Armor#Medium-0", 1),
        ("Heavy", "https://helldivers.wiki.gg/wiki/Armor#Heavy-0", 2)
    ]
    armor_categories = {"Light": [], "Medium": [], "Heavy": []}
    armor_urls = {}
    
    try:
        for cat_name, url, table_index in target_infos:
            print(f" => 위키 페이지({cat_name}) 표 탐색 로딩 중: {url}")
            driver.get(url)
            
            try:
                WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.wikitable")))
            except:
                print(f"   ({cat_name} 테이블을 찾을 수 없거나 타임아웃 되었습니다.)")
                continue
                
            tables = driver.find_elements(By.CSS_SELECTOR, "table.wikitable")
            if len(tables) > table_index:
                rows = tables[table_index].find_elements(By.TAG_NAME, "tr")
                for row in rows:
                    if row.find_elements(By.TAG_NAME, "th"):
                        continue
                    tds = row.find_elements(By.TAG_NAME, "td")
                    if len(tds) >= 2:
                        links = tds[1].find_elements(By.TAG_NAME, "a")
                        if links:
                            name = links[0].text.strip()
                            if name and name not in armor_categories[cat_name]:
                                armor_categories[cat_name].append(name)
                                try:
                                    img_tag = tds[0].find_element(By.TAG_NAME, "img")
                                    thumb_src = img_tag.get_attribute("src")
                                    armor_urls[name] = thumb_to_full(thumb_src)
                                except:
                                    url_name = name.replace(" ", "_").replace("\"", "%22")
                                    armor_urls[name] = f"https://helldivers.wiki.gg/wiki/Special:FilePath/{url_name}_Armor_Render.png"
                                
        total_found = sum(len(lst) for lst in armor_categories.values())
        print(f"위키에서 총 {total_found}개의 갑옷 이름을 성공적으로 찾았습니다.")
        cookies = driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    finally:
        driver.quit()
 
    print("\n=== 멀티프로세싱 다운로드 및 WebP 변환 시작 ===")
    tasks = []
    ARMOR_CAT_MAP = {"Light": "경량", "Medium": "일반", "Heavy": "중량"}
    
    for cat, names in armor_categories.items():
        mapped_cat = ARMOR_CAT_MAP.get(cat, cat)
        cat_dir = os.path.join(base_dir, "방어구", mapped_cat)
        os.makedirs(cat_dir, exist_ok=True)
        for name in names:
            if name in downloaded_armors:
                print(f" => [패스] '{name}' 은(는) 이미 다운로드된 기록이 있습니다.")
                continue
            img_url = armor_urls.get(name)
            tasks.append((cat, name, cat_dir, record_file, cookie_str, img_url))
 
    if tasks:
        pool_size = min(os.cpu_count() or 4, workers, len(tasks))
        print(f" => 병렬 다운로드 시작 (프로세스 수: {pool_size})")
        with Pool(processes=pool_size) as pool:
            results = pool.map(download_armor_task, tasks)
        for success, name, cat, safe_name, error_msg in results:
            if success:
                mapped_cat = ARMOR_CAT_MAP.get(cat, cat)
                print(f"   => 성공! 사진 다운로드 및 WebP 변환 완료 (방어구/{mapped_cat}/{safe_name}.webp)")
                with open(record_file, "a", encoding="utf-8") as f:
                    f.write(f"{name}\n")
                downloaded_armors.add(name)
            else:
                print(f"   => 실패! [{name}] 다운로드 중 에러가 발생했습니다: {error_msg}")
    else:
        print("다운로드할 새로운 이미지가 없습니다.")


# 5. 스트라타젬 (Stratagem) 수집
def scrape_stratagem_images(output_dir=None, record_file=None, headless=True, workers=4):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = output_dir if output_dir else script_dir
    os.makedirs(base_dir, exist_ok=True)
    if not record_file:
        record_file = os.path.join(base_dir, "downloaded_stratagems.txt")
    else:
        record_file = os.path.abspath(record_file)
        
    downloaded_stratagems = set()
    if os.path.exists(record_file):
        with open(record_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    downloaded_stratagems.add(line.strip())
                    
    print(f"이전에 저장된 스트라타젬 정보: {len(downloaded_stratagems)}개")

    driver = _make_driver(headless=headless)
    cookie_str = ""
    categories_map = {
        "공격": ["Orbital_Strikes", "Eagle_Strikes"],
        "방어": ["Emplacements", "Sentries"],
        "보급": ["Support_Weapons", "Backpacks", "Vehicles"],
        "임무": ["Ship", "Objective", "Other", "Mission_Stratagems"]
    }
    url = "https://helldivers.wiki.gg/wiki/Stratagems"
    stratagem_categories = {cat: [] for cat in categories_map.keys()}
    stratagem_urls = {}
    
    try:
        print(f" => 스트라타젬 위키 페이지 로딩 중...")
        driver.get(url)
        try:
            WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.wikitable")))
        except:
            print("   (위키 테이블을 찾을 수 없거나 타임아웃 되었습니다.)")
            return
            
        for cat_name, ids in categories_map.items():
            for header_id in ids:
                print(f"   => 카테고리 [{cat_name}] 의 헤더 ID '{header_id}' 탐색 중...")
                xpath_query = f"//span[@id='{header_id}']/ancestor::*[self::h2 or self::h3]/following-sibling::table[contains(@class, 'wikitable')][1]"
                try:
                    table = driver.find_element(By.XPATH, xpath_query)
                except:
                    continue
                rows = table.find_elements(By.TAG_NAME, "tr")
                for row in rows:
                    if row.find_elements(By.TAG_NAME, "th"):
                        continue
                    tds = row.find_elements(By.TAG_NAME, "td")
                    if len(tds) >= 2:
                        links = tds[1].find_elements(By.TAG_NAME, "a")
                        if links:
                            name = links[0].text.strip()
                            if name and name not in stratagem_categories[cat_name]:
                                stratagem_categories[cat_name].append(name)
                                try:
                                    img_tag = tds[0].find_element(By.TAG_NAME, "img")
                                    thumb_src = img_tag.get_attribute("src")
                                    stratagem_urls[name] = thumb_to_full(thumb_src)
                                except:
                                    url_name = name.replace(" ", "_").replace("\"", "%22")
                                    stratagem_urls[name] = [f"https://helldivers.wiki.gg/wiki/Special:FilePath/{url_name}_Stratagem_Icon.svg"]
                                    
        total_found = sum(len(lst) for lst in stratagem_categories.values())
        print(f"위키에서 총 {total_found}개의 스트라타젬 이름을 성공적으로 찾았습니다.")
        cookies = driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    finally:
        driver.quit()
        
    print("\n=== 멀티프로세싱 다운로드 및 WebP 변환 시작 ===")
    tasks = []
    
    for cat_name, names in stratagem_categories.items():
        cat_dir = os.path.join(base_dir, "스트라타젬", cat_name)
        os.makedirs(cat_dir, exist_ok=True)
        for name in names:
            if name in downloaded_stratagems:
                print(f" => [패스] '{name}' 은(는) 이미 다운로드된 기록이 있습니다.")
                continue
            img_urls = stratagem_urls.get(name)
            tasks.append((cat_name, name, cat_dir, record_file, cookie_str, img_urls))
            
    if tasks:
        pool_size = min(os.cpu_count() or 4, workers, len(tasks))
        print(f" => 병렬 다운로드 시작 (프로세스 수: {pool_size})")
        with Pool(processes=pool_size) as pool:
            results = pool.map(download_stratagem_task, tasks)
        for success, name, cat, safe_name, error_msg in results:
            if success:
                print(f"   => 성공! 사진 다운로드 및 변환 완료 ({cat}/{safe_name}.webp)")
                with open(record_file, "a", encoding="utf-8") as f:
                    f.write(f"{name}\n")
                downloaded_stratagems.add(name)
            else:
                print(f"   => 실패! [{name}] 다운로드 중 에러가 발생했습니다: {error_msg}")
    else:
        print("다운로드할 새로운 이미지가 없습니다.")


# 6. 무기 (Weapon) 수집
def scrape_weapon_images(output_dir=None, record_file=None, headless=True, workers=4):
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    base_dir = output_dir if output_dir else script_dir
    os.makedirs(base_dir, exist_ok=True)
    if not record_file:
        record_file = os.path.join(base_dir, "downloaded_weapons.txt")
    else:
        record_file = os.path.abspath(record_file)

    downloaded_weapons = set()
    if os.path.exists(record_file):
        with open(record_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    downloaded_weapons.add(line.strip())
    print(f"이전에 저장된 무기 정보: {len(downloaded_weapons)}개")

    main_driver = _make_driver(headless=headless)
    cookie_str  = ""
    all_weapons = {}
    
    CAT_MAP = {
        "primary": "주 무기",
        "secondary": "보조 무기",
        "throwable": "투척 무기"
    }

    try:
        # Weapons 페이지에서 무기목록 + 썸네일 URL 한 번에 수집
        url = "https://helldivers.wiki.gg/wiki/Weapons"
        print(f" => Weapons 페이지 로딩: {url}")
        main_driver.get(url)

        try:
            WebDriverWait(main_driver, 15).until(EC.presence_of_element_located((By.ID, "Weaponry")))
        except Exception:
            print("   (Weaponry 섹션을 찾지 못했습니다. Cloudflare 차단일 수 있습니다.)")
        time.sleep(1)

        main_tabs = [("primary", "Primary"), ("secondary", "Secondary"), ("throwable", "Throwable")]
        for cat_key, tab_name in main_tabs:
            all_weapons[cat_key] = {}
            try:
                tab_el = main_driver.find_element(By.ID, f"{tab_name}-0-label")
                main_driver.execute_script("arguments[0].click();", tab_el)
                time.sleep(0.8)
            except:
                pass

            try:
                tab_content = main_driver.find_element(By.ID, f"{tab_name}-0")
                sub_labels = tab_content.find_elements(By.CSS_SELECTOR, "[id$='-label']")
            except:
                sub_labels = []
                continue

            for sub_label in sub_labels:
                label_id = sub_label.get_attribute("id") or ""
                if not label_id: continue
                try:
                    main_driver.execute_script("arguments[0].click();", sub_label)
                    time.sleep(0.4)
                except:
                    pass

                content_id = label_id.replace("-label", "")
                w_class = re.sub(r'-\d+$', '', content_id).replace("_", " ")

                name_sel  = f"#{content_id} > div > ul > li > div > div.gallerytext > big > a"
                img_sel   = f"#{content_id} > div > ul > li > div > div.thumb > div > a > img"

                name_links = main_driver.find_elements(By.CSS_SELECTOR, name_sel)
                img_tags   = main_driver.find_elements(By.CSS_SELECTOR, img_sel)

                pairs = []
                for i, link in enumerate(name_links):
                    name = link.text.strip()
                    if not name: continue
                    img_url = None
                    if i < len(img_tags):
                        src = img_tags[i].get_attribute("src") or ""
                        img_url = thumb_to_full(src)
                    pairs.append((name, img_url))

                if pairs:
                    all_weapons[cat_key][w_class] = pairs
                    found_names = [p[0] for p in pairs]
                    print(f"   [{cat_key}] {w_class}: {len(pairs)}개 → {found_names}")

        total = sum(len(pairs) for classes in all_weapons.values() for pairs in classes.values())
        print(f"\n총 {total}개 무기 발견")

        # 갤러리 썸네일 URL이 없는 무기 선별
        missing = []
        for cat_key, classes in all_weapons.items():
            for w_class, pairs in classes.items():
                for name, url in pairs:
                    if url is None and name not in downloaded_weapons:
                        missing.append((name, cat_key, headless))

        cookies = main_driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    finally:
        main_driver.quit()

    # 2단계: 썸네일 URL이 없는 무기 → 멀티스레드로 File: 페이지에서 URL 탐색
    fallback_urls = {}
    if missing:
        print(f"\n => 썸네일 URL 없는 무기 {len(missing)}개에 대해 병렬 URL 탐색 시작...")
        max_workers = min(workers, len(missing))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch_weapon_url, m): m for m in missing}
            for future in as_completed(futures):
                name, url = future.result()
                fallback_urls[name] = url
                status = "OK" if url else "실패"
                print(f"   [{status}] {name}: {url or '-'}")

    # url None 항목을 fallback으로 채우기
    for cat_key, classes in all_weapons.items():
        for w_class, pairs in classes.items():
            all_weapons[cat_key][w_class] = [
                (name, url if url else fallback_urls.get(name))
                for name, url in pairs
            ]

    # 3단계: 멀티프로세싱 다운로드 + 50% 리사이즈 + 1920x1080 캔버스 + WebP 변환
    print("\n=== 멀티프로세싱 다운로드 및 WebP 변환 시작 ===")
    tasks = []
    for cat_key, classes in all_weapons.items():
        mapped_cat = CAT_MAP.get(cat_key, cat_key)
        cat_dir = os.path.join(base_dir, mapped_cat)
        for w_class, pairs in classes.items():
            for name, img_url in pairs:
                if name in downloaded_weapons:
                    print(f" => [패스] '{name}'")
                    continue
                if not img_url:
                    print(f" => [건너뜀] '{name}' - URL 없음")
                    continue
                tasks.append((cat_key, w_class, name, cat_dir, record_file, cookie_str, img_url))

    if tasks:
        pool_size = min(os.cpu_count() or 4, workers, len(tasks))
        print(f" => 병렬 다운로드 시작 (프로세스 수: {pool_size})")
        with Pool(processes=pool_size) as pool:
            results = pool.map(download_weapon_task, tasks)

        for success, name, cat, w_class, safe_name, target_dir, error_msg in results:
            rel_path = os.path.relpath(os.path.join(target_dir, f"{safe_name}.webp"), base_dir)
            if success:
                print(f"   => 성공! ({rel_path})")
                with open(record_file, "a", encoding="utf-8") as f:
                    f.write(f"{name}\n")
                downloaded_weapons.add(name)
            else:
                print(f"   => 실패! [{name}]: {error_msg}")
    else:
        print("다운로드할 새로운 이미지가 없습니다.")

# ==============================================================================
# ─── 대화형 및 CLI 제어 UI 모듈 ───────────────────────────────────────────────
# ==============================================================================

def interactive_mode():
    print("=" * 60)
    print("  Helldivers 2 Wiki-gg Scraper - 대화형 실행 모드")
    print("=" * 60)
    print("  명령줄 인자 없이 바로 실행되어 대화형 메뉴로 전환합니다.")
    print("  더블클릭하거나 일반 실행 시 편리하게 수집할 수 있습니다.")
    print("=" * 60)
    print("  [1] 전체 카테고리 수집 (All)")
    print("  [2] 부스터 (Booster) 수집")
    print("  [3] 망토 (Cape) 수집")
    print("  [4] 헬멧 (Helmet) 수집")
    print("  [5] 방어구 (Armor) 수집")
    print("  [6] 스트라타젬 (Stratagems) 수집")
    print("  [7] 무기 (Weapon) 수집")
    print("  [0] 프로그램 종료")
    print("=" * 60)
    
    choices = ["booster", "cape", "helmet", "armor", "stratagems", "weapon"]
    
    while True:
        try:
            user_input = input("\n▶ 수집할 번호를 입력하세요 (다중 선택은 쉼표 예: 2,3,5 / 종료는 0): ").strip()
            if not user_input:
                continue
            if user_input == "0":
                print("프로그램을 종료합니다.")
                sys.exit(0)
                
            selected_numbers = [x.strip() for x in user_input.split(",")]
            run_targets = []
            
            for num in selected_numbers:
                if num == "1":
                    return choices, False  # 전체 실행
                elif num == "2": run_targets.append("booster")
                elif num == "3": run_targets.append("cape")
                elif num == "4": run_targets.append("helmet")
                elif num == "5": run_targets.append("armor")
                elif num == "6": run_targets.append("stratagems")
                elif num == "7": run_targets.append("weapon")
                else:
                    print(f"[!] 잘못된 번호 입력이 포함되어 있습니다: '{num}'")
                    break
            else:
                if run_targets:
                    return list(set(run_targets)), True
        except (KeyboardInterrupt, SystemExit):
            sys.exit(0)
        except Exception as e:
            print(f"[!] 입력 분석 중 오류 발생: {e}")

def main():
    choices = ["booster", "cape", "helmet", "armor", "stratagems", "weapon"]
    is_interactive = len(sys.argv) == 1
    
    run_targets = []
    output_dir = None
    cache_file = None
    headless = True
    workers = 4
    
    if is_interactive:
        run_targets, confirm_needed = interactive_mode()
        
        ans_headless = input("\n▶ 크롬 창을 보이지 않게 백그라운드에서 실행할까요? (Y/n): ").strip().lower()
        headless = ans_headless not in ["n", "no", "false"]
        
        ans_output = input("▶ 커스텀 저장 폴더명을 지정할까요? (비워두면 기본 한글 폴더에 다운로드): ").strip()
        if ans_output:
            output_dir = ans_output
            
        print("\n" + "=" * 60)
        print(" 🌌 크롤링 작업을 시작합니다. 완료될 때까지 기다려 주세요!")
        print("=" * 60)
    else:
        parser = argparse.ArgumentParser(
            description="Helldivers 2 Wiki-gg Assets Integrated Scraper CLI",
            formatter_class=argparse.RawTextHelpFormatter
        )
        
        parser.add_argument(
            "targets",
            nargs="*",
            choices=choices,
            help="크롤링할 대상을 지정합니다. (선택 가능: " + ", ".join(choices) + ")"
        )
        
        parser.add_argument(
            "--all",
            action="store_true",
            help="모든 대상(booster, cape, helmet, armor, stratagems, weapon)을 순차적으로 크롤링합니다."
        )
        
        parser.add_argument(
            "-o", "--output",
            default=None,
            help="이미지들이 다운로드되어 저장될 출력 디렉토리 경로입니다. (기본값: 스크립트 실행 위치)"
        )
        
        parser.add_argument(
            "-c", "--cache",
            default=None,
            help="다운로드된 내역을 기록하는 캐시 텍스트 파일의 경로입니다."
        )
        
        parser.add_argument(
            "--no-headless",
            action="store_true",
            help="Chrome 브라우저 구동 시 화면을 띄우는 Non-headless 모드로 실행합니다. (기본값은 백그라운드 구동)"
        )
        
        parser.add_argument(
            "-w", "--workers",
            type=int,
            default=4,
            help="병렬 다운로드 시 활용할 최대 프로세스/스레드 수입니다. (기본값: 4)"
        )
        
        args = parser.parse_args()
        
        if args.all:
            run_targets = choices
        else:
            run_targets = args.targets
            
        if not run_targets:
            parser.print_help()
            print("\n[오류] 크롤링할 대상을 1개 이상 지정하거나 --all 옵션을 전달해 주세요.")
            input("\n[도움말 확인] 엔터 키를 누르면 종료됩니다...")
            sys.exit(1)
            
        output_dir = args.output
        cache_file = args.cache
        headless = not args.no_headless
        workers = args.workers
        
    print("=" * 60)
    print(" ★ Helldivers 2 Wiki-gg Scraper - CLI 통합 실행기 ★ ")
    print("=" * 60)
    print(f"▶ 실행 타겟: {', '.join(run_targets)}")
    print(f"▶ 출력 경로: {output_dir if output_dir else '현재 실행 폴더 (상대 경로)'}")
    print(f"▶ 헤드리스 모드: {'활성화 (백그라운드)' if headless else '비활성화 (브라우저 화면 켬)'}")
    print(f"▶ 병렬 다운로드 수 (Workers): {workers}")
    print("=" * 60 + "\n")
    
    target_map = {
        "booster": {
            "name": "부스터 (Booster)",
            "func": scrape_booster_images,
            "cache_file": "downloaded_booster.txt"
        },
        "cape": {
            "name": "망토 (Cape)",
            "func": scrape_cape_images,
            "cache_file": "downloaded_cape.txt"
        },
        "helmet": {
            "name": "헬멧 (Helmet)",
            "func": scrape_helmet_images,
            "cache_file": "downloaded_armors.txt"
        },
        "armor": {
            "name": "방어구 (Armor)",
            "func": scrape_armor_images,
            "cache_file": "downloaded_armors.txt"
        },
        "stratagems": {
            "name": "스트라타젬 (Stratagems)",
            "func": scrape_stratagem_images,
            "cache_file": "downloaded_stratagems.txt"
        },
        "weapon": {
            "name": "무기 (Weapon)",
            "func": scrape_weapon_images,
            "cache_file": "downloaded_weapons.txt"
        }
    }
    
    for t_key in run_targets:
        info = target_map[t_key]
        print(f">> [{info['name']}] 크롤링을 시작합니다...")
        print("-" * 50)
        
        t_cache = cache_file
        if not t_cache and output_dir:
            t_cache = os.path.join(output_dir, info["cache_file"])
            
        try:
            info["func"](
                output_dir=output_dir,
                record_file=t_cache,
                headless=headless,
                workers=workers
            )
            print("-" * 50)
            print(f"[OK] [{info['name']}] 크롤링 작업이 성공적으로 완료되었습니다!\n")
        except Exception as e:
            print("-" * 50)
            print(f"[ERROR] [{info['name']}] 크롤링 실패! 에러 발생: {e}\n")
            
    print("=" * 60)
    print(" ★ 모든 타겟의 크롤링 작업 및 리소스 처리가 종료되었습니다! ★")
    print("=" * 60)
    
    input("\n[완료] 프로그램이 성공적으로 끝났습니다. 엔터 키를 누르면 종료됩니다...")

if __name__ == "__main__":
    main()
