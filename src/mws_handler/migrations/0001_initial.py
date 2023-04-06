# Generated by Django 4.1.6 on 2023-04-06 14:25

from django.db import migrations, models
import django.db.models.deletion
import mws_handler.models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_id', models.CharField(default=uuid.uuid4, max_length=255, unique=True)),
                ('timestamp', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='ScriptSession',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('process_name', models.CharField(blank=True, max_length=255)),
                ('session_id', models.CharField(default=mws_handler.models.create_new_id, max_length=255, unique=True)),
                ('start_time', models.DateTimeField(auto_now=True)),
                ('end_time', models.DateTimeField(auto_now=True)),
                ('slack_thread_id', models.CharField(blank=True, max_length=255)),
                ('user_enabled', models.BooleanField(default=False)),
                ('status', models.CharField(choices=[('inactive', 'Inactive'), ('active', 'Active'), ('completed', 'Completed'), ('error', 'Error')], default='inactive', max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('viewed', models.BooleanField(default=False)),
                ('timestamp', models.DateTimeField(auto_now=True)),
                ('event', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='mws_handler.event')),
            ],
        ),
        migrations.AddField(
            model_name='event',
            name='session',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='mws_handler.scriptsession'),
        ),
    ]
