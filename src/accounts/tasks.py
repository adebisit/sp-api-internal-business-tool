from django.contrib.auth.models import User
from .models import *

SLACK = {
    "stevenhollander": "UAAUDU94P",
    "joanna86": "U019F7CEW15",
    "Jennifer": "U01UV0GED54",
    "Percival": "U037JTGQZ98",
    "Mary": "U02C95H5LQ1",
    "Josh": "UQRDHEXSS"
}

def test():
    UserProfile.objects.all().delete()
    users = User.objects.all()
    for user in users:
        profile = UserProfile(
            user=user,
            slack_user_id=SLACK[user.username]
        )
        profile.save()
