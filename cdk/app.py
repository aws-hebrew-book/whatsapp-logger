#!/usr/bin/env python3
import os

import aws_cdk as cdk

from cdk.whatsapp_listener_stack import WhatsAppListener
from cdk.googlesheets_recorder_stack import GoogleSheetsRecorder

app = cdk.App()
stage = app.node.try_get_context("stage") or "dev"
googlesheets_recorder = GoogleSheetsRecorder(app, f"GoogleSheetRecorder-{stage}")
whatsapp_listener = WhatsAppListener(app, f"WhatsAppWebListener-{stage}", whatsapp_messages=googlesheets_recorder.whatsapp_message_sns)

app.synth()
