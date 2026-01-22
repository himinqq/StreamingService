import logging
import boto3
from pathlib import Path
from datetime import datetime, timedelta

from botocore.exceptions import ClientError

import config


class VideoProcessor:
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.original_filename = filepath.name
        self.video_info = {}
        self.parsed_data = {}

    def _parse_info_light(self):
        """MoviePy 없이 경로 기반으로 메타데이터 추출 (안전한 버전)"""
        parts = self.filepath.parts

        try:
            # 1. 기준 폴더 위치 찾기 ('processing' 또는 'ready')
            # config.PROCESSING_DIR.name은 'processing'입니다.
            if config.PROCESSING_DIR.name in parts:
                base_index = parts.index(config.PROCESSING_DIR.name)
            elif config.BASE_DIR.name in parts:
                # 'processing' 폴더가 없는 예외 상황을 위해 'ready' 폴더를 보조 기준으로 사용
                base_index = parts.index(config.BASE_DIR.name)
            else:
                raise ValueError(f"경로에서 '{config.PROCESSING_DIR.name}'를 찾을 수 없습니다.")

            # 2. 날짜/시간 파싱
            # 파일명(stem)은 '20260119-123000' 형식이어야 합니다.
            created_at_utc = datetime.strptime(self.filepath.stem, "%Y%m%d-%H%M%S")

            # 3. UUID 및 스트림 시작 시간 추출 (인덱스 에러 방지)
            # 구조: .../processing/[UUID]/[Session_ID]/[File].mp4
            self.parsed_data = {
                "blackbox_uuid": parts[base_index + 1],
                "stream_started_at_str": parts[base_index + 2],
                "created_at_kst": self._change_utc_to_kst(created_at_utc),
                "file_type": self.filepath.suffix[1:],
                "file_size": self.filepath.stat().st_size,
                "duration": 0.0,  # 분석 워커에서 채움
            }

            # 스트림 시작 시간(Session ID) 처리
            if self.parsed_data["stream_started_at_str"] == "offline":
                self.parsed_data["stream_started_at_kst"] = datetime(1970, 1, 1, 0, 0, 0)
            else:
                start_time_utc = datetime.strptime(self.parsed_data["stream_started_at_str"], "%Y%m%d-%H%M%S")
                self.parsed_data["stream_started_at_kst"] = self._change_utc_to_kst(start_time_utc)

        except (ValueError, IndexError, KeyError) as e:
            # 에러 발생 시 상세 경로와 원인을 로그로 남기고 상위로 던짐
            logging.error(f" 경로 파싱 실패! 파일: {self.filepath}")
            logging.error(f" 원인: {type(e).__name__} - {e}")
            logging.error(f" 현재 경로 구조(parts): {parts}")
            raise  # 워커(workers.py)의 except 블록에서 캐치하게 함

    def _generate_new_names(self):
        """
        object_key 생성 로직 유지!
        이 키는 파일명/시간 기반이므로 MoviePy 없어도 생성 가능합니다.
        """
        created_at_kst = self.parsed_data["created_at_kst"]
        blackbox_uuid = self.parsed_data["blackbox_uuid"]
        file_type = self.parsed_data["file_type"]

        # 프론트엔드가 요청할 최종 키 형식
        new_filename_kst = created_at_kst.strftime("%Y%m%d-%H%M%S") + f".{file_type}"
        new_s3_key = f"{blackbox_uuid}/{new_filename_kst}"

        self.video_info = {
            "blackbox_uuid": blackbox_uuid,
            "stream_started_at": self.parsed_data["stream_started_at_kst"].isoformat(),
            "created_at": created_at_kst.isoformat(),
            "file_size": self.parsed_data["file_size"],
            "duration": self.parsed_data["duration"],  # 현재는 0
            "object_key": new_s3_key,  # ⭐ 중요: 여기서 키가 확정됨
            "file_type": file_type,
        }

    def _upload_to_s3(self) -> str | None:
        """S3 업로드. 실패 시 None 반환."""
        s3_key = self.video_info.get("object_key")
        if not s3_key: return None

        s3_client = boto3.client('s3')
        try:
            s3_client.upload_file(str(self.filepath), config.S3_BUCKET_NAME, s3_key)
            region = s3_client.meta.region_name
            s3_url = f"https://{config.S3_BUCKET_NAME}.s3.{region}.amazonaws.com/{s3_key}"
            logging.info(f"S3 업로드 성공. URL: {s3_url}")
            return s3_url
        except ClientError as e:
            logging.error(f"S3 업로드 실패: {e}")
            return None

    @staticmethod
    def _change_utc_to_kst(utc_time):
        return utc_time + timedelta(hours=9)