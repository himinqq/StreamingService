# scanner.py
import logging
import config
import global_state


class LocalFileWatcher:
    def __init__(self, base_dir):
        self.base_dir = base_dir

    def scan_and_put_to_queue(self):
        # 1. 내 로컬 폴더(ready)에서 mp4 파일 목록만 가져옴
        new_videos = list(self.base_dir.glob('**/*.mp4'))

        if not new_videos:
            return

        for source_path in new_videos:
            # ⭐ 핵심: 직접 처리하지 않고, global_state의 WORK_QUEUE에 일감만 넣음
            # 이렇게 해야 workers.py에 있는 스레드들이 일을 나눠서 함
            logging.info(f"파일 발견, 큐에 추가: {source_path.name}")
            global_state.WORK_QUEUE.put(type('Job', (), {'filepath': source_path}))


def main_scanner_loop():
    """main.py에서 주기적으로 호출할 함수 (무한 루프 제거)"""
    watcher = LocalFileWatcher(config.BASE_DIR)
    watcher.scan_and_put_to_queue()  # 한 번만 스캔하고 끝냄