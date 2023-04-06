
from io import BytesIO
from slack_sdk import WebClient
from django.conf import settings
import os

if settings.SLACK_BOT_TOKEN is None or settings.SLACK_SCRIPT_UPDATE_CHANNEL is None:
	clients = None
else:
	client = WebClient(token=settings.SLACK_BOT_TOKEN)


def notify_slack(channel, blocks, message, ts):
	if client is None:
		return None
	response = client.chat_postMessage(
		channel=channel,
		thread_ts=ts,
		text=message,
		blocks=blocks,
	)
	
	return response.data.get("ts")


def upload_file_slack(channel, ts, file_content, filename="response", file_extension="csv"):
	if client is None:
		return None
	data_byte = bytes(file_content, 'ascii')
	file = BytesIO()
	file.write(data_byte)
	file.seek(0)
	response = client.files_upload(
		channels=channel,
		thread_ts=ts,
		file=file,
		initial_comment="<@UAAUDU94P>",
		filename=f"{filename}.{file_extension}",
		filetype=file_extension,
		title="SP API Feed Response"
	)
	file.close()
	return response.data.get("ts")


def create_block(**kwargs):
	is_thread = kwargs.get("is_thread", False)
	title = kwargs["title"]
	session_id = kwargs["session_id"]
	description = kwargs.get("description", "No Descriptions")
	records = kwargs.get("records")
	mentions = kwargs.get("mentions", False)

	if is_thread:
		title += f"\n[Session-ID: {session_id}]"
	notification_block = [{
		"type": "header",
		"text": {
			"type": "plain_text",
			"text": title,
			"emoji": True
		}
	}]


	if mentions:
		notification_block.append({
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": "<@UAAUDU94P>"
			}
		})

	if records:
		notification_block.append({
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": f"{description}"
			}
		})
	else:
		notification_block.append({
			"type": "section",
			"text": {
				"type": "plain_text",
				"text": f"{description}",
				"emoji": True
			}
		})

	if is_thread:
		notification_block.append({
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": "Updates will be provided in the thread of this message."
			}
		})


	return notification_block
