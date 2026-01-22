# scanner.py
import time
import logging
import config
import global_state
import metrics

# 기존 workers.py에서 가벼워진 PrimaryWorker만 가져옵니다.
# (RetryScheduler, RetryWorker는 삭제했으므로 import하지 않습니다)
from workers import PrimaryWorker
from scanner import main_scanner_loop  # 기존 scanner.py에 있던 루프 함수 로직

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)


def main():
    # 1. 메트릭 서버 시작 (프로메테우스 모니터링용)
    metrics.start_metrics_server()

    # 2. SQS 전송 워커 시작
    # 예전처럼 무거운 분석을 하는 게 아니라, 
    # [S3 업로드 -> SQS 전송 -> 파일 삭제]만 하는 가벼운 스레드입니다.
    # config.NUM_WORKERS는 보통 1~2 정도로 충분합니다.
    logging.info(f"{config.NUM_WORKERS}개의 SQS 전송(1차) 워커를 시작합니다.")
    for _ in range(config.NUM_WORKERS):
        worker = PrimaryWorker()
        worker.daemon = True  # 메인 프로세스 죽으면 같이 죽도록
        worker.start()

    # ❌ 삭제됨: RetryScheduler (SQS가 알아서 재시도함)
    # ❌ 삭제됨: RetryWorker (SQS Visibility Timeout이 대체함)

    # 3. 메인 스캐너 루프 시작
    logging.info("파일 감시(Scanner) 루프를 시작합니다.")

    try:
        while True:
            # 디렉토리를 스캔해서 새로운 파일을 global_state.WORK_QUEUE에 넣음
            main_scanner_loop()

            # 상태 로그 출력
            logging.info(
                f"다음 스캔까지 {config.SCAN_INTERVAL_SECONDS}초 대기... "
                f"(대기 중인 전송 작업: {global_state.WORK_QUEUE.qsize()})"
            )

            # 대기
            time.sleep(config.SCAN_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logging.info("종료 요청을 받았습니다. 스캐너를 종료합니다.")


if __name__ == "__main__":
    main()