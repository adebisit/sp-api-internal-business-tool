from django.db import models
from uuid import uuid4

from utils import slackbot
import random
import string
# Create your models here.
from datetime import datetime
from django.conf import settings


def create_new_id():
    now = datetime.now()
    while True:
        session_id = f'S{"".join(random.choice(string.ascii_uppercase))}{now.strftime("%m%d%H%M%S")}'
        if ScriptSession.objects.filter(session_id=session_id).count() == 0:
            break
    return session_id


class ScriptSession(models.Model):
    process_name = models.CharField(max_length=255, blank=True)
    session_id = models.CharField(max_length=255, default=create_new_id, unique=True)
    start_time = models.DateTimeField(auto_now=True)
    end_time = models.DateTimeField(auto_now=True)
    slack_thread_id = models.CharField(max_length=255, blank=True)
    user_enabled = models.BooleanField(default=False)

    STATUS_CHOICES = (
        ('inactive', "Inactive"),
        ('active', "Active"),
        ('completed', "Completed"),
        ('error', "Error")
    )
    status = models.CharField(max_length=255, choices=STATUS_CHOICES, default="inactive")

    def create_event(self, title, description=""):
        event = Event(
            session=self,
            title=title,
            description=description
        )
        event.save()
        return event


class Event(models.Model):
    session = models.ForeignKey(
        ScriptSession, on_delete=models.CASCADE, null=True)
    event_id = models.CharField(max_length=255, default=uuid4, unique=True)
    timestamp = models.DateTimeField(auto_now=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    def create_notification(self):
        notification = Notification(event=self)
        notification.save()
        return notification


class Notification(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, null=True)
    viewed = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now=True)

    def send(self, records=None):
        message = f"Update Session ID {self.event.session.session_id}"
        message += f"{self.event.title}\n{self.event.description}"
        blocks = slackbot.create_block(
            title=self.event.title.upper(),
            session_id=self.event.session.session_id,
            description=self.event.description if self.event.description else "No Descriptions",
            records=records,
            is_thread=self.event.session.slack_thread_id is None or self.event.session.slack_thread_id == "",
            mentions=(not self.event.session.user_enabled)
        )
        
        ts = slackbot.notify_slack(
            channel=settings.SLACK_SCRIPT_UPDATE_CHANNEL if self.event.session.user_enabled else "script-failures",
            ts=self.event.session.slack_thread_id,
            message=self.event.title,
            blocks=blocks
        )
        if self.event.session.slack_thread_id is None or self.event.session.slack_thread_id == "":
            self.event.session.slack_thread_id = ts
            self.event.session.save()

    def upload_file(self, content):
        slackbot.upload_file_slack(
            channel=settings.SLACK_SCRIPT_UPDATE_CHANNEL if self.event.session.user_enabled else "script-failures",
            ts=self.event.session.slack_thread_id,
            file_content=content
        )
