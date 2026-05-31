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
        # 0.5초에서 1.5초 랜덤 딜레이 후 이미지 서버로 직접 요청
        time.sleep(random.uniform(0.5, 1.5))
        req = urllib.request.Request(img_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            img_data = response.read()
            
        # png로 디스크에 우선 저장
        with open(png_path, 'wb') as out_file:
            out_file.write(img_data)
            
        # 디스크의 png 파일을 열어서 WebP로 변환 후 저장
        image = Image.open(png_path)
        image.save(webp_path, "WEBP")
        image.close()
        
        # 원본 png 파일 삭제
        if os.path.exists(png_path):
            os.remove(png_path)
        
        return True, name, cat, safe_name, None
    except urllib.error.HTTPError as e:
        return False, name, cat, safe_name, f"HTTP Error {e.code}: {e.reason} ({img_url})"
    except Exception as e:
        if os.path.exists(png_path):
            try:
                os.remove(png_path)
            except:
                pass
        return False, name, cat, safe_name, str(e)


def scrape_armor_images(output_dir=None, record_file=None, headless=True, workers=4):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 출력 경로 결정
    base_dir = output_dir if output_dir else script_dir
    os.makedirs(base_dir, exist_ok=True)
    
    # 캐시 파일 결정
    if not record_file:
        record_file = os.path.join(base_dir, "downloaded_armors.txt")
    else:
        record_file = os.path.abspath(record_file)
        
    # 나중에 다시 코드를 실행했을 때 중복 스킵을 위한 저장 기록 불러오기
    downloaded_armors = set()
    if os.path.exists(record_file):
        with open(record_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    downloaded_armors.add(line.strip())
                    
    print(f"이전에 저장된 갑옷 정보: {len(downloaded_armors)}개")

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
    
    target_infos = [
        ("Light", "https://helldivers.wiki.gg/wiki/Armor#Light-0", 0),
        ("Medium", "https://helldivers.wiki.gg/wiki/Armor#Medium-0", 1),
        ("Heavy", "https://helldivers.wiki.gg/wiki/Armor#Heavy-0", 2)
    ]
    
    armor_categories = {"Light": [], "Medium": [], "Heavy": []}
    armor_urls = {} # name -> url mapping
    
    try:
        for cat_name, url, table_index in target_infos:
            print(f" => 위키 페이지({cat_name}) 표 탐색 로딩 중: {url}")
            driver.get(url)
            
            try:
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
                            if name and name not in armor_categories[cat_name]:
                                armor_categories[cat_name].append(name)
                                
                                # 썸네일 경로에서 원본 이미지 원스톱 추출!
                                try:
                                    img_tag = tds[0].find_element(By.TAG_NAME, "img")
                                    thumb_src = img_tag.get_attribute("src")
                                    # src 형태: ".../images/thumb/x/y/name.png/120px-name.png"
                                    if "/thumb/" in thumb_src:
                                        parts = thumb_src.split("/")
                                        # 맨 뒤(해상도) 제거
                                        parts.pop()
                                        # "/thumb" 제거
                                        parts.remove("thumb")
                                        img_url = "/".join(parts)
                                    else:
                                        img_url = thumb_src
                                        
                                    if img_url.startswith("//"):
                                        img_url = "https:" + img_url
                                        
                                    armor_urls[name] = img_url
                                except:
                                    # 썸네일을 못 찾으면 이전 fallback 포맷 사용
                                    url_name = name.replace(" ", "_").replace("\"", "%22")
                                    armor_urls[name] = f"https://helldivers.wiki.gg/wiki/Special:FilePath/{url_name}_Armor_Render.png"
                                
        total_found = sum(len(lst) for lst in armor_categories.values())
        print(f"위키에서 총 {total_found}개의 갑옷 이름을 성공적으로 찾았습니다.")
        for cat, names in armor_categories.items():
            print(f" └─ {cat} 카테고리: {len(names)}개")
            
        cookies = driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        
    finally:
        driver.quit()
 
    print("\n=== 멀티프로세싱 다운로드 및 WebP 변환 시작 ===")
    
    tasks = []
    ARMOR_CAT_MAP = {
        "Light": "경량",
        "Medium": "일반",
        "Heavy": "중량"
    }
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
        # 이젠 순수 이미지 서버를 타격하므로 Cloudflare가 덜 빡빡함. 최대 4개 프로세스 속도 유지!
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
            
    print("\n=== 모든 작업이 완전히 종료되었습니다. ===")
 
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Helldivers 2 Armor Image Scraper")
    parser.add_argument("-o", "--output", help="Output directory to save images", default=None)
    parser.add_argument("-c", "--cache", help="Cache file to record downloaded items", default=None)
    parser.add_argument("--no-headless", action="store_true", help="Run chrome browser in non-headless mode")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Number of parallel download processes")
    args = parser.parse_args()
    
    scrape_armor_images(
        output_dir=args.output,
        record_file=args.cache,
        headless=not args.no_headless,
        workers=args.workers
    )
