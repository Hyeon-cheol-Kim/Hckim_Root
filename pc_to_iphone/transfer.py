"""iPhone AFC 파일 전송 모듈 (pymobiledevice3 기반)"""

import os
from pathlib import Path

ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.html', '.py', '.c', '.cpp', '.java', '.bat', '.sh'}
TARGET_FOLDER = '내다운로드'


def get_connected_device():
    """연결된 iPhone 정보 반환. 없으면 None."""
    try:
        from pymobiledevice3.lockdown import create_using_usbmux
        lockdown = create_using_usbmux()
        name = lockdown.get_value('', 'DeviceName') or 'iPhone'
        udid = lockdown.udid
        return {'name': name, 'udid': udid, 'lockdown': lockdown}
    except Exception as e:
        return None


def check_device_status():
    """기기 연결 상태 문자열 반환."""
    info = get_connected_device()
    if info:
        return True, f"연결됨: {info['name']} ({info['udid'][:8]}...)"
    return False, "iPhone 연결 안 됨 (USB 케이블 및 신뢰 설정 확인)"


def transfer_files(file_paths, progress_callback=None, status_callback=None):
    """
    파일 목록을 iPhone의 TARGET_FOLDER 로 전송한다.

    progress_callback(current, total) : 진행률 알림
    status_callback(message)          : 상태 텍스트 알림

    Returns: (성공 수, 실패 목록 [(파일명, 오류메시지), ...])
    """
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    def _cb_status(msg):
        if status_callback:
            status_callback(msg)

    def _cb_progress(cur, tot):
        if progress_callback:
            progress_callback(cur, tot)

    _cb_status("iPhone 연결 중...")
    lockdown = create_using_usbmux()

    success_count = 0
    failures = []
    total = len(file_paths)

    with AfcService(lockdown=lockdown) as afc:
        # 대상 폴더 생성
        try:
            afc.makedirs(TARGET_FOLDER)
        except Exception:
            pass  # 이미 존재하면 무시

        for idx, filepath in enumerate(file_paths, start=1):
            filename = os.path.basename(filepath)
            target_path = f"{TARGET_FOLDER}/{filename}"
            _cb_status(f"전송 중 ({idx}/{total}): {filename}")
            _cb_progress(idx - 1, total)

            try:
                with open(filepath, 'rb') as f:
                    data = f.read()
                afc.set_file_contents(target_path, data)
                success_count += 1
            except Exception as e:
                failures.append((filename, str(e)))

            _cb_progress(idx, total)

    return success_count, failures


def is_allowed(filepath):
    return Path(filepath).suffix.lower() in ALLOWED_EXTENSIONS
