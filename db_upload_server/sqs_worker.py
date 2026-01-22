import json
import boto3
import requests
import os
from moviepy.editor import VideoFileClip
import config


def process_sqs_message():
    sqs = boto3.client('sqs')
    s3 = boto3.client('s3')

    # 1. 메시지 수신 (Long Polling)
    response = sqs.receive_message(
        QueueUrl=config.SQS_QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=20
    )

    if 'Messages' not in response:
        return  # 메시지 없음

    message = response['Messages'][0]
    receipt_handle = message['ReceiptHandle']
    body = json.loads(message['Body'])

    bucket = body['bucket']
    key = body['object_key']
    video_info = body['metadata']  # Ingestion에서 넘겨준 기초 정보

    local_tmp_path = f"/tmp/{os.path.basename(key)}"

    try:
        # 2. S3에서 파일 다운로드 (분석용)
        s3.download_file(bucket, key, local_tmp_path)

        # 3. 🎬 무거운 작업 수행 (MoviePy)
        with VideoFileClip(local_tmp_path) as clip:
            real_duration = clip.duration

        # 4. 메타데이터 완성 (Duration 채우기)
        video_info['duration'] = real_duration

        # 5. ⭐ 상태 서버로 전송 (이제 유저가 조회 가능!)
        # 프론트엔드는 이 시점 이후부터 object_key를 알게 됨
        res = requests.post(config.STATUS_SERVER_URL, json=video_info)
        res.raise_for_status()

        # 6. 메시지 삭제 (처리 완료)
        sqs.delete_message(QueueUrl=config.SQS_QUEUE_URL, ReceiptHandle=receipt_handle)
        print(f" [성공] 영상 처리 완료 및 DB 저장 성공: {key}")

    except Exception as e:
        print(f"Processing Failed: {e}")
        # 실패 시 메시지를 안 지우면 SQS가 알아서 재시도 처리함 (Visibility Timeout)
    finally:
        if os.path.exists(local_tmp_path):
            os.remove(local_tmp_path)


if __name__ == "__main__":
    while True:
        process_sqs_message()