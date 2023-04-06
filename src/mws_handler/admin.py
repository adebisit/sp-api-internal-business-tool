from django.contrib import admin
from .models import ScriptSession, Event, Notification
# Register your models here.


class NotificationInline(admin.TabularInline):
    model = Notification


class EventInline(admin.TabularInline):
    model = Event


@admin.register(ScriptSession)
class ScriptSessionAdmin(admin.ModelAdmin):
    inline = (EventInline,)
    list_display = (
        "session_id",
        "start_time",
        "end_time"
    )


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    inline = (NotificationInline,)
    list_display = (
        "session",
        "event_id",
        "timestamp",
        "title",
        "description"
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "timestamp",
        "viewed",
    )
