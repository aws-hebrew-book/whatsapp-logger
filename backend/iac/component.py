from .constrcuts.state import State
from .constrcuts.configuration import Configuration
from .constrcuts.admin_panel import AdminPanel
from .constrcuts.googlesheets_recorder import GoogleSheetsRecorder
from .utils.cdk_utils import prepare_layer

from constructs import Construct

from aws_cdk import (
    Stack,
    CfnOutput,
    aws_events as eb,
    aws_sns as sns,
    aws_s3 as s3,
)


class Backend(Stack):
    @property
    def event_bus(self) -> eb.EventBus:
        return self._event_bus

    @property
    def whatsapp_message_sns(self) -> sns.Topic:
        return self._recorder.whatsapp_message_sns

    @property
    def qr_bucket(self) -> s3.Bucket:
        return self._state.qr_bucket

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._event_bus = eb.EventBus(self, "WhatsAppSystemBus")
        self._state = State(self, "State")
        configuration = Configuration(self, "Configuration")
        layer = prepare_layer(
            self, layer_name="BackendLocalReq", poetry_dir="backend/admin-panel"
        )
        panel = AdminPanel(
            self,
            "AdminPanel",
            self._state.qr_bucket,
            configuration.admin_password_secret,
            configuration.google_credentials_secret,
            configuration.sheet_url_parameter,
            self._event_bus,
            self._state.state_table,
            layer,
        )
        self._recorder = GoogleSheetsRecorder(
            self,
            "GoogleSheetsRecorder",
            configuration.google_credentials_secret,
            configuration.sheet_url_parameter,
            layer,
        )

        CfnOutput(
            self,
            "AdminPasswordURL",
            value=f"https://{self.region}.console.aws.amazon.com/secretsmanager/secret?name={configuration.admin_password_secret.secret_name}",
        )

        CfnOutput(
            self,
            "AdminURL",
            value=panel.lambda_url,
        )