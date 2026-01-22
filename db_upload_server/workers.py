# workers.py (Ingestion Pod용)
import os
import json
import logging
import boto3
from threading import Thread

import config
import global_state
from video_processor import VideoProcessor

class PrimaryWorker(Thread):
    def run(self):
        sqs = boto3.client('sqs', region_name=config.AWS_DEFAULT_REGION)

        while True:
            job_item = global_state.WORK_QUEUE.get()
            processor = VideoProcessor(job_item.filepath)

            try:
                # 1. 가벼운 파싱 (Key 생성)
                processor._parse_info_light()
                processor._generate_new_names()

                # 2. S3 업로드 (파일은 제자리에 갖다 둠)
                s3_url = processor._upload_to_s3()
                if not s3_url: raise Exception("S3 Upload Failed")

                # 3. 🚨 상태 서버 전송 건너뜀! (Duration이 없으므로)
                # 대신 SQS 메시지 전송
                message_body = {
                    "bucket": config.S3_BUCKET_NAME,
                    "object_key": processor.video_info["object_key"],  # 생성된 키
                    "metadata": processor.video_info  # 현재까지 파악된 정보
                }

                sqs.send_message(
                    QueueUrl=config.SQS_QUEUE_URL,
                    MessageBody=json.dumps(message_body)
                )

                # 4. 로컬 파일 삭제 (EBS 비우기)
                os.remove(job_item.filepath)

            except Exception as e:
                logging.error(f"Error: {e}")
                # 재시도 로직...
            finally:
                global_state.WORK_QUEUE.task_done()