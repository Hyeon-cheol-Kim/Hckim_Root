import sys
import os
import re
import csv
import glob
import chardet  # 인코딩 감지를 위해 추가

def ensure_utf8_encoding(file_path):
    """파일의 인코딩을 감지하여 UTF-8이 아닌 경우 UTF-8로 변환하고 원본을 백업합니다."""
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()

        if not raw_data:
            return True  # 빈 파일은 변환 생략

        detected = chardet.detect(raw_data)
        encoding = detected['encoding']

        # 이미 UTF-8이거나 ASCII인 경우 변환 없이 진행 (utf-8-sig = BOM 있는 UTF-8도 포함)
        if encoding and encoding.lower() in ['utf-8', 'ascii', 'utf-8-sig']:
            return True

        # chardet가 인코딩 감지 실패 시 처리 불가
        if encoding is None:
            print(f"  [인코딩 변환 실패] 인코딩을 감지할 수 없습니다.")
            return False

        # UTF-8 변환 작업 진행
        print(f"  [인코딩 변환] {encoding} -> UTF-8 변환 중...")
        content = raw_data.decode(encoding)

        # 원본 파일 백업 (.bak)
        backup_path = file_path + ".bak"
        if os.path.exists(backup_path):
            os.remove(backup_path) # 기존 백업 파일이 있으면 삭제
        os.rename(file_path, backup_path)

        # UTF-8로 재저장
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  [변환 완료] 원본 백업됨: {os.path.basename(backup_path)}")
        return True

    except Exception as e:
        print(f"  [인코딩 변환 실패] {e}")
        return False

def parse_eom_final_package(input_path):
    # 파일 읽기 전 UTF-8 인코딩 유효성 검사 및 변환
    if not ensure_utf8_encoding(input_path):
        print(f" [오류] 인코딩 문제로 파일을 처리할 수 없습니다: {input_path}")
        return

    # 정규식 패턴들
    re_steps_caps = re.compile(r'TimingMaxSteps\s+(\d+)\s+TimingMaxOffset\s+(\d+)\s+VoltageMaxSteps\s+(\d+)\s+VoltageMaxOffset\s+(\d+)')
    re_data = re.compile(r'lane:\s*(\d+)\s+timing:\s*(-?\d+)\s+voltage:\s*(-?\d+)\s+error_cnt:\s*(\d+)')
    lane_data = {}
    config_info = ""
    t_max, v_max = 63, 63

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
            caps_match = re_steps_caps.search(content)
            if caps_match:
                t_max_val, t_off, v_max_val, v_off = caps_match.groups()
                t_max, v_max = int(t_max_val), int(v_max_val)
                config_info = f"TimingMaxSteps:{t_max_val}, TimingMaxOffset:{t_off}, VoltageMaxSteps:{v_max_val}, VoltageMaxOffset:{v_off}"

            f.seek(0)
            for line in f:
                data_match = re_data.search(line)
                if data_match:
                    l_id = int(data_match.group(1))
                    t, v, val = int(data_match.group(2)), int(data_match.group(3)), int(data_match.group(4))
                    if l_id not in lane_data:
                        lane_data[l_id] = {}
                    curr_map = lane_data[l_id]
                    key = (t, v)
                    # 63이 아닌 유효 값 우선 병합 로직
                    if key not in curr_map or (curr_map[key] == 63 and val != 63) or (val != 63 and val < curr_map[key]):
                        curr_map[key] = val
    except Exception as e:
        print(f" [오류] 파일을 읽을 수 없습니다: {e}")
        return

    if not lane_data:
        return

    base_dir = os.path.dirname(os.path.abspath(input_path))
    file_name_only = os.path.splitext(os.path.basename(input_path))[0]

    # 1. Result_입력파일명_QC_Offsets.txt 생성
    existing_lanes = sorted(lane_data.keys())
    offset_path = os.path.join(base_dir, f"Result_{file_name_only}_QC_Offsets.txt")
    with open(offset_path, 'w', encoding='utf-8') as f:
        if 0 in existing_lanes and 1 in existing_lanes:
            f.write("DualLane\n")
        elif 0 in existing_lanes:
            f.write("SingleLane 0\n")
        elif 1 in existing_lanes:
            f.write("SingleLane 1\n")
        else:
            f.write(f"SingleLane {existing_lanes}\n")
        f.write(f"{config_info}\n")

    # 2. Result_입력파일명_laneX.csv 생성
    for l_id in existing_lanes:
        output_path = os.path.join(base_dir, f"Result_{file_name_only}_lane{l_id}.csv")
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # A1 셀: LaneX
            writer.writerow([f'Lane{l_id}'] + list(range(-t_max, t_max + 1)))
            # Voltage 내림차순 (Max -> Min)
            for v_idx in range(v_max, -v_max - 1, -1):
                row_data = [v_idx]
                for t_idx in range(-t_max, t_max + 1):
                    row_data.append(lane_data[l_id].get((t_idx, v_idx), 63))
                writer.writerow(row_data)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        parse_eom_final_package(sys.argv[1])
    else:
        print("탐색 중: EOM 폴더 내의 EOM 파일들...")
        eom_folders = [d for d in glob.glob('EOM*') if os.path.isdir(d)]
        if not eom_folders:
            print("현재 경로에 'EOM'으로 시작하는 폴더가 없습니다.")
        else:
            for folder in eom_folders:
                print(f"\n[폴더 진입] {folder}")
                target_files = glob.glob(os.path.join(folder, 'EOM*'))
                for file_path in target_files:
                    fname = os.path.basename(file_path)
                    # 결과 파일 중복 처리 방지
                    if os.path.isfile(file_path) and not fname.startswith('Result_') and not fname.endswith(('.csv', '.txt', '.bak')):
                        print(f" [처리 중] {fname}")
                        parse_eom_final_package(file_path)
            print("\n모든 작업이 완료되었습니다.")
