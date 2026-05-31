import os
import re
import time
import urllib.request
import urllib.error
import random
from multiprocessing import Pool
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ─── 카테고리 한글 매핑 사전 ───────────────────────────────────────
CAT_MAP = {
    "primary": "주 무기",
    "secondary": "보조 무기",
    "throwable": "투척 무기"
}

W_CLASS_MAP = {
    "Assault Rifle": "돌격 소총",
    "Assault_Rifle": "돌격 소총",
    "Energy-Based": "에너지계",
    "Explosive": "폭발성",
    "Marksman Rifle": "지정사수소총",
    "Marksman_Rifle": "지정사수소총",
    "Shotgun": "산탄총",
    "Special": "특수",
    "Submachine Gun": "기관단총",
    "Submachine_Gun": "기관단총",
    "Melee": "근접",
    "Pistol": "권총",
    "Standard": "표준"
}


# ─── 이미지 다운로드 + WebP 변환 (멀티프로세싱) ────────────────────────────────

def download_weapon_task(args):
    cat, w_class, name, cat_dir, record_file, cookie_str, img_url = args

    safe_name = (name.replace("/", "_").replace("\\", "_").replace(":", "_")
                     .replace("*", "_").replace("?", "_").replace("\"", "_")
                     .replace("<", "_").replace(">", "_").replace("|", "_"))
    mapped_w_class = W_CLASS_MAP.get(w_class, w_class)
    safe_w_class = mapped_w_class.replace("/", "_")
    target_dir = os.path.join(cat_dir, safe_w_class)
    os.makedirs(target_dir, exist_ok=True)

    webp_path = os.path.join(target_dir, f"{safe_name}.webp")
    png_path  = os.path.join(target_dir, f"{safe_name}.png")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Accept':     'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
        'Referer':    'https://helldivers.wiki.gg/'
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
        try:
            os.remove(png_path)
        except:
            pass

    return False, name, cat, w_class, safe_name, target_dir, err


# ─── 썸네일 src → 원본 URL 변환 ──────────────────────────────────────────────

def thumb_to_full(src):
    """
    wiki.gg 썸네일 URL → 원본 이미지 URL
    예: https://...static.../thumb/a/ab/File.png/200px-File.png
        → https://...static.../a/ab/File.png
    """
    if not src:
        return None
    if "/thumb/" in src:
        parts = src.split("/")
        parts.pop()               # 200px-File.png 제거
        parts.remove("thumb")     # thumb 제거
        src = "/".join(parts)
    if src.startswith("//"):
        src = "https:" + src
    return src


# ─── 병렬 URL 탐색 (멀티스레딩: 스레드별 Chrome 드라이버) ────────────────────

def _make_driver(headless=True):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('--headless')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    return webdriver.Chrome(options=options)


def _fetch_weapon_url(args):
    """
    스레드 내에서 각 무기의 Weapons 페이지 갤러리 썸네일 src를 가져옵니다.
    """
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

        # File: 페이지에서 원본 이미지 링크 추출
        for sel in [".fullImageLink a", "#file a", "a.internal", "div.fullMedia a"]:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                href = el.get_attribute("href") or ""
                if href and ("upload" in href or ".png" in href.lower()):
                    return name, href

        # img 태그 폴백
        for img in driver.find_elements(By.CSS_SELECTOR, "img"):
            src = img.get_attribute("src") or ""
            if "upload" in src and "_Render" in src:
                return name, thumb_to_full(src)

        return name, None

    except Exception as e:
        return name, None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


# ─── Weapons 페이지 파싱 (메인 드라이버, 단일 세션) ──────────────────────────

def scrape_weapons_from_page(driver):
    """
    Weapons 페이지에서 탭(Primary/Secondary/Throwable) > 클래스 > 갤러리 아이템 구조로
    {cat_key: {w_class: [(name, thumb_url), ...]}} 반환
    """
    url = "https://helldivers.wiki.gg/wiki/Weapons"
    print(f" => Weapons 페이지 로딩: {url}")
    driver.get(url)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "Weaponry"))
        )
    except Exception:
        print("   (Weaponry 섹션을 찾지 못했습니다. Cloudflare 차단일 수 있습니다.)")

    time.sleep(1)

    result = {}
    main_tabs = [
        ("primary",   "Primary"),
        ("secondary", "Secondary"),
        ("throwable", "Throwable"),
    ]

    for cat_key, tab_name in main_tabs:
        result[cat_key] = {}

        # 메인 탭 클릭
        try:
            tab_el = driver.find_element(By.ID, f"{tab_name}-0-label")
            driver.execute_script("arguments[0].click();", tab_el)
            time.sleep(0.8)
        except Exception:
            print(f"   [{cat_key}] 탭 '{tab_name}-0-label' 클릭 실패 (탭이 없거나 이미 활성)")

        # 탭 컨텐츠 내 서브 클래스 레이블 탐색
        try:
            tab_content = driver.find_element(By.ID, f"{tab_name}-0")
            sub_labels = tab_content.find_elements(By.CSS_SELECTOR, "[id$='-label']")
        except Exception:
            sub_labels = []
            print(f"   [{cat_key}] 탭 컨텐츠 '{tab_name}-0' 를 찾지 못했습니다.")
            continue

        if not sub_labels:
            print(f"   [{cat_key}] 서브 레이블 없음")
            continue

        for sub_label in sub_labels:
            label_id = sub_label.get_attribute("id") or ""
            if not label_id:
                continue

            # 서브 클래스 탭 클릭
            try:
                driver.execute_script("arguments[0].click();", sub_label)
                time.sleep(0.4)
            except Exception:
                pass

            content_id = label_id.replace("-label", "")  # 예: "Assault_Rifle-0", "Special-1"
            w_class = re.sub(r'-\d+$', '', content_id).replace("_", " ")  # 예: "Assault Rifle", "Special"

            # 무기 이름 셀렉터
            name_sel  = f"#{content_id} > div > ul > li > div > div.gallerytext > big > a"
            # 썸네일 이미지 셀렉터
            img_sel   = f"#{content_id} > div > ul > li > div > div.thumb > div > a > img"

            name_links = driver.find_elements(By.CSS_SELECTOR, name_sel)
            img_tags   = driver.find_elements(By.CSS_SELECTOR, img_sel)

            pairs = []
            for i, link in enumerate(name_links):
                name = link.text.strip()
                if not name:
                    continue
                img_url = None
                if i < len(img_tags):
                    src = img_tags[i].get_attribute("src") or ""
                    img_url = thumb_to_full(src)
                pairs.append((name, img_url))

            if pairs:
                result[cat_key][w_class] = pairs
                found_names = [p[0] for p in pairs]
                print(f"   [{cat_key}] {w_class}: {len(pairs)}개 → {found_names}")
            else:
                print(f"   [{cat_key}] {w_class}: 무기 없음 (content_id={content_id})")

    return result


# ─── 메인 ─────────────────────────────────────────────────────────────────────

def scrape_weapon_images(output_dir=None, record_file=None, headless=True, workers=4):
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    
    # 출력 경로 결정
    base_dir = output_dir if output_dir else script_dir
    os.makedirs(base_dir, exist_ok=True)
    
    # 캐시 파일 결정
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

    try:
        # 1단계: Weapons 페이지에서 무기목록 + 썸네일 URL 한 번에 수집
        all_weapons = scrape_weapons_from_page(main_driver)

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

    print("\n=== 모든 작업이 완전히 종료되었습니다. ===")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Helldivers 2 Weapon Image Scraper")
    parser.add_argument("-o", "--output", help="Output directory to save images", default=None)
    parser.add_argument("-c", "--cache", help="Cache file to record downloaded items", default=None)
    parser.add_argument("--no-headless", action="store_true", help="Run chrome browser in non-headless mode")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Number of parallel download processes")
    args = parser.parse_args()
    
    scrape_weapon_images(
        output_dir=args.output,
        record_file=args.cache,
        headless=not args.no_headless,
        workers=args.workers
    )
