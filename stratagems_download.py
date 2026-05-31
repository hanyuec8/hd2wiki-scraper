import os
import time
import urllib.request
import urllib.error
import io
import random
from multiprocessing import Pool
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def download_stratagem_task(args):
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
    
    if isinstance(img_urls, str):
        urls_to_try = [img_urls]
    else:
        urls_to_try = img_urls
        
    for img_url in urls_to_try:
        if not img_url:
            continue
            
        try:
            time.sleep(random.uniform(0.3, 1.0))
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


def scrape_stratagem_images(output_dir=None, record_file=None, headless=True, workers=4):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 출력 경로 결정
    base_dir = output_dir if output_dir else script_dir
    os.makedirs(base_dir, exist_ok=True)
    
    # 캐시 파일 경로 결정
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
    
    cookie_str = ""
    
    # 카테고리별 매핑 정의
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
            WebDriverWait(driver, 25).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.wikitable"))
            )
        except:
            print("   (위키 테이블을 찾을 수 없거나 타임아웃 되었습니다.)")
            return
            
        for cat_name, ids in categories_map.items():
            for header_id in ids:
                print(f"   => 카테고리 [{cat_name}] 의 헤더 ID '{header_id}' 탐색 중...")
                
                # XPath로 해당 ID를 가진 span 바로 뒤 형제 table.wikitable 요소 찾기
                xpath_query = f"//span[@id='{header_id}']/ancestor::*[self::h2 or self::h3]/following-sibling::table[contains(@class, 'wikitable')][1]"
                
                try:
                    table = driver.find_element(By.XPATH, xpath_query)
                except:
                    # 해당 ID를 직접 가진 요소나 헤더가 없을 수 있으므로 예외 처리
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
                                    
                                    if "/thumb/" in thumb_src:
                                        parts = thumb_src.split("/")
                                        parts.pop()
                                        parts.remove("thumb")
                                        img_url = "/".join(parts)
                                    else:
                                        img_url = thumb_src
                                        
                                    if img_url.startswith("//"):
                                        img_url = "https:" + img_url
                                        
                                    stratagem_urls[name] = img_url
                                except:
                                    url_name = name.replace(" ", "_").replace("\"", "%22")
                                    stratagem_urls[name] = [
                                        f"https://helldivers.wiki.gg/wiki/Special:FilePath/{url_name}_Stratagem_Icon.svg"
                                    ]
                                    
        total_found = sum(len(lst) for lst in stratagem_categories.values())
        print(f"위키에서 총 {total_found}개의 스트라타젬 이름을 성공적으로 찾았습니다.")
        
        cookies = driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        
    finally:
        driver.quit()
        
    print("\n=== 멀티프로세싱 다운로드 및 WebP 변환 시작 ===")
    
    tasks = []
    
    for cat_name, names in stratagem_categories.items():
        cat_dir = os.path.join(base_dir, cat_name)
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
        
    print("\n=== 모든 작업이 완전히 종료되었습니다. ===")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Helldivers 2 Stratagem Image Scraper")
    parser.add_argument("-o", "--output", help="Output directory to save images", default=None)
    parser.add_argument("-c", "--cache", help="Cache file to record downloaded items", default=None)
    parser.add_argument("--no-headless", action="store_true", help="Run chrome browser in non-headless mode")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Number of parallel download processes")
    args = parser.parse_args()
    
    scrape_stratagem_images(
        output_dir=args.output,
        record_file=args.cache,
        headless=not args.no_headless,
        workers=args.workers
    )
