from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import TYPE_CHECKING, Dict, List
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

from ....utils.chats_data_lake import AggregatedGroup, ChatsDataLake

from ...utils.consts import SUMMARY_PREFIX

if TYPE_CHECKING:
    from mypy_boto3_s3.service_resource import Bucket


logger = Logger()


@logger.inject_lambda_context(log_event=True)
def handler(event, context: LambdaContext):
    lake = ChatsDataLake()
    chats = _collect_chats(lake)
    files = _write_to_s3(chats, lake.bucket)
    return {"s3_files": files}


def _collect_chats(lake: ChatsDataLake) -> Dict[str, AggregatedGroup]:
    yesterday = datetime.now(tz=timezone.utc) - timedelta(days=1)
    return_value = lake.get_all_chats(yesterday)
    logger.info("Appended chats", count=len(return_value))

    return return_value


def _write_to_s3(groups: Dict[str, AggregatedGroup], bucket: Bucket) -> List[dict]:
    files_to_return: List[dict] = []
    for group in groups:
        group_dict = {
            "group_name": groups[group].group_name,
            "group_id": groups[group].group_id,
            "chats": "",
        }

        sorted_chats = sorted(groups[group].chats, key=lambda val: val.time_of_chat)
        chats_str = "\n".join(
            [f"{chat.participant_name} said {chat.message}" for chat in sorted_chats]
        )

        group_dict["chats"] = chats_str
        file_name = f"{groups[group].group_id}-{groups[group].group_name}.json".replace(
            "/", "_"
        )
        # Convert the group dictionary to a JSON string and write to S3
        file_name = f"{SUMMARY_PREFIX}/{file_name}"
        file_content = json.dumps(group_dict)
        bucket.put_object(Key=file_name, Body=file_content.encode())
        files_to_return.append({"file_name": file_name})
    return files_to_return
