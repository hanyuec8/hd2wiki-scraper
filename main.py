import os
import sys
import argparse

# 로컬 크롤러 모듈 임포트
try:
    from booster_download import scrape_booster_images
    from cape_download import scrape_cape_images
    from helmet_download import scrape_helmet_images
    from armor_download import scrape_armor_images
    from stratagems_download import scrape_stratagem_images
    from weapon_download import scrape_weapon_images
except ImportError as e:
    # main.py가 위치한 폴더를 sys.path에 추가하여 직접 실행 시 임포트 에러 방지
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from booster_download import scrape_booster_images
    from cape_download import scrape_cape_images
    from helmet_download import scrape_helmet_images
    from armor_download import scrape_armor_images
    from stratagems_download import scrape_stratagem_images
    from weapon_download import scrape_weapon_images

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
                    return list(set(run_targets)), True  # 중복 제거 후 반환, 개별 타겟 모드
        except (KeyboardInterrupt, SystemExit):
            sys.exit(0)
        except Exception as e:
            print(f"[!] 입력 분석 중 오류 발생: {e}")

def main():
    choices = ["booster", "cape", "helmet", "armor", "stratagems", "weapon"]
    
    # 인자 유무 확인: 인자가 아예 없거나 더블클릭 실행인 경우
    is_interactive = len(sys.argv) == 1
    
    run_targets = []
    output_dir = None
    cache_file = None
    headless = True
    workers = 4
    
    if is_interactive:
        # 대화형 모드 구동
        run_targets, confirm_needed = interactive_mode()
        
        # 대화형 모드 추가 설정 입력
        ans_headless = input("\n▶ 크롬 창을 보이지 않게 백그라운드에서 실행할까요? (Y/n): ").strip().lower()
        headless = ans_headless not in ["n", "no", "false"]
        
        ans_output = input("▶ 커스텀 저장 폴더명을 지정할까요? (비워두면 기본 한글 폴더에 다운로드): ").strip()
        if ans_output:
            output_dir = ans_output
            
        print("\n" + "=" * 60)
        print(" 🌌 크롤링 작업을 시작합니다. 완료될 때까지 기다려 주세요!")
        print("=" * 60)
    else:
        # 기존 CLI 인수 파싱
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
            # CLI에서 잘못 썼을 때 바로 꺼지지 않도록 유도 (혹시 더블클릭 방지)
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
    
    # 각 타겟별 실행 맵핑
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
        
        # 개별 캐시 파일 경로 계산
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
    
    # 더블클릭 실행 시 즉시 창 닫힘 방지!
    input("\n[완료] 프로그램이 성공적으로 끝났습니다. 엔터 키를 누르면 종료됩니다...")

if __name__ == "__main__":
    main()
