"""AmazonApp URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import include

from django.urls import path, re_path
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.http.response import HttpResponse
from rest_framework.authtoken.views import obtain_auth_token



def home_view(request):
    return HttpResponse("Welcome to SP-API-Handler API")

urlpatterns = [
    path('', home_view),
    path('api/token/', obtain_auth_token, name='api_token_auth'),
    re_path(r'admin/', admin.site.urls),
    re_path('api/', include('api.urls', 'api'))
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)