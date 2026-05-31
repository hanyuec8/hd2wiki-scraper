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
    
    if isinstance(img_urls, str):
        urls_to_try = [img_urls]
    else:
        urls_to_try = img_urls
        
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
            try:
                os.remove(png_path)
            except:
                pass
        return False, name, cat, safe_name, " | ".join(error_msgs)
        
    return True, name, cat, safe_name, None


def scrape_cape_images(output_dir=None, record_file=None, headless=True, workers=4):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 출력 경로 결정
    base_dir = output_dir if output_dir else script_dir
    os.makedirs(base_dir, exist_ok=True)
    
    # 캐시 파일 경로 결정
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

    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('--headless')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36')
    
    # 봇 자동화 도구 탐지 우회를 위한 기본 설정
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=options)
    
    # 브라우저에 webdriver가 실행 중이라는 흔적을 지우는 자바스크립트 실행
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            })
        '''
    })
    
    cookie_str = ""
    
    target_infos = [
        ("Cape", "https://helldivers.wiki.gg/wiki/Armor#Cape-0", 4)
    ]
    
    cape_categories = {"Cape": []}
    cape_urls = {}
    
    try:
        for cat_name, url, table_index in target_infos:
            print(f" => 위키 페이지({cat_name}) 표 탐색 로딩 중...")
            driver.get(url)
            
            try:
                # Cloudflare 확인 창이 뜰 경우 수동으로 체크할 수 있도록 대기 시간을 25초로 늘렸습니다.
                WebDriverWait(driver, 25).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table.wikitable"))
                )
            except:
                print(f"   ({cat_name} 테이블을 찾을 수 없거나 타임아웃 되었습니다.)")
                continue
                
            tables = driver.find_elements(By.CSS_SELECTOR, "table.wikitable")
            
            if len(tables) > table_index:
                target_table = tables[table_index]
                
                rows = target_table.find_elements(By.TAG_NAME, "tr")
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
                                    
                                    if "/thumb/" in thumb_src:
                                        parts = thumb_src.split("/")
                                        parts.pop()
                                        parts.remove("thumb")
                                        img_url = "/".join(parts)
                                    else:
                                        img_url = thumb_src
                                        
                                    if img_url.startswith("//"):
                                        img_url = "https:" + img_url
                                        
                                    cape_urls[name] = img_url
                                except:
                                    url_name = name.replace(" ", "_").replace("\"", "%22")
                                    cape_urls[name] = [
                                        f"https://helldivers.wiki.gg/wiki/Special:FilePath/{url_name}_Cape_Render.png"
                                    ]
                                
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
            
    print("\n=== 모든 작업이 완전히 종료되었습니다. ===")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Helldivers 2 Cape Image Scraper")
    parser.add_argument("-o", "--output", help="Output directory to save images", default=None)
    parser.add_argument("-c", "--cache", help="Cache file to record downloaded items", default=None)
    parser.add_argument("--no-headless", action="store_true", help="Run chrome browser in non-headless mode")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Number of parallel download processes")
    args = parser.parse_args()
    
    scrape_cape_images(
        output_dir=args.output,
        record_file=args.cache,
        headless=not args.no_headless,
        workers=args.workers
    )