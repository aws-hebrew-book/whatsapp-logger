from constructs import Construct
from aws_cdk import (
    aws_lambda_python_alpha as lambda_python,
    aws_lambda as _lambda,
    Duration,
    aws_s3 as s3,
    aws_sns as sns,
    aws_kinesisfirehose_alpha as fh,
    aws_kinesisfirehose_destinations_alpha as destinations,
    aws_secretsmanager as secretmanager,
    aws_events as events,
    aws_events_targets as targets,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
    aws_logs as logs,
)

from .sns_sqs import SnsSqsConnection


class ChatGPTIntegration(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        chats_bucket: s3.Bucket,
        layer: lambda_python.PythonLayerVersion,
        whatsapp_messages: sns.Topic,
        chatgpt_key: secretmanager.Secret,
        event_bus: events.EventBus,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        s3_destination = destinations.S3Bucket(
            bucket=chats_bucket,
            buffering_interval=Duration.seconds(900),
            data_output_prefix="!{timestamp:yyyy}.!{timestamp:MM}.!{timestamp:dd}/",
            error_output_prefix="myFirehoseFailures/!{firehose:error-output-type}/Year=!{timestamp:yyyy}/Month=!{timestamp:MM}/Day=!{timestamp:dd}",
        )

        ds = fh.DeliveryStream(self, "Delivery Stream", destinations=[s3_destination])

        write_chats_to_s3 = lambda_python.PythonFunction(
            self,
            "ChatGPTIntegration",
            runtime=_lambda.Runtime.PYTHON_3_9,
            entry="backend",
            index="src/chatgpt_integration/functions/write_chats_to_s3/app.py",
            timeout=Duration.seconds(30),
            layers=[layer],
            environment={
                "CHATS_FIREHOSE": ds.delivery_stream_name,
            },
        )

        summerize_chats = lambda_python.PythonFunction(
            self,
            "SummerizeChats",
            runtime=_lambda.Runtime.PYTHON_3_9,
            entry="backend",
            index="src/chatgpt_integration/functions/summerize_chats/app.py",
            timeout=Duration.seconds(120),
            layers=[layer],
            environment={
                "CHATS_BUCKET": chats_bucket.bucket_name,
            },
        )

        chatgpt_call = lambda_python.PythonFunction(
            self,
            "ChatGPTCall",
            runtime=_lambda.Runtime.PYTHON_3_9,
            entry="backend",
            index="src/chatgpt_integration/functions/chatgpt_call/app.py",
            timeout=Duration.seconds(60),
            layers=[layer],
            environment={
                "OPENAI_KEY": chatgpt_key.secret_name,
                "CHATS_BUCKET": chats_bucket.bucket_name,
            },
        )

        state_machine = self._build_stf(summerize_chats, chatgpt_call, event_bus)

        schedule_expression = events.Schedule.expression(
            "cron(0 1 * * ? *)"
        )  # Runs at 1:00:00 AM UTC every day
        events.Rule(
            self,
            "MyScheduledRule",
            schedule=schedule_expression,
            targets=[targets.SfnStateMachine(machine=state_machine)],
        )

        ds.grant_put_records(write_chats_to_s3)
        chatgpt_key.grant_read(chatgpt_call)
        chats_bucket.grant_put(summerize_chats)
        chats_bucket.grant_read(summerize_chats)
        chats_bucket.grant_read(chatgpt_call)

        SnsSqsConnection(self, "WriteToS3", whatsapp_messages, write_chats_to_s3)

    def _build_stf(
        self,
        summerize_chats: lambda_python.PythonFunction,
        chatgpt_call: lambda_python.PythonFunction,
        event_bus: events.EventBus,
    ) -> sfn.StateMachine:
        summerize_step = sfn_tasks.LambdaInvoke(
            self,
            "Summerize Chats",
            lambda_function=summerize_chats,
        )

        send_to_chatgpt = sfn_tasks.LambdaInvoke(
            self,
            "Send to ChatGPT",
            lambda_function=chatgpt_call,
        )

        send_to_eventbridge = sfn_tasks.EventBridgePutEvents(
            self,
            "Send an event to EventBridge",
            entries=[
                sfn_tasks.EventBridgePutEventsEntry(
                    detail=sfn.TaskInput.from_json_path_at("$.Payload"),
                    source="chatgpt",
                    detail_type="summary",
                    event_bus=event_bus,
                )
            ],
        )

        map = sfn.Map(
            self, "Map State", max_concurrency=2, input_path="$.Payload.s3_files"
        )

        success = sfn.Succeed(self, "All summery messages were sent")

        map.iterator(send_to_chatgpt.next(send_to_eventbridge))

        definition = summerize_step.next(map).next(success)
        return sfn.StateMachine(
            self,
            "SendToChatGPT",
            definition=definition,
            timeout=Duration.minutes(5),
            logs=sfn.LogOptions(
                destination=logs.LogGroup(self, "MyLogGroup"), level=sfn.LogLevel.ALL
            ),
        )