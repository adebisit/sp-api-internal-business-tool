from django.urls import path
from . import views
from rest_framework.authtoken.views import obtain_auth_token


app_name = "api"

urlpatterns = [
     path('token-auth/', obtain_auth_token, name='token_auth'),
     path('items/add/', views.AddToInventory.as_view()),
     path('orders/', views.GetOrdersData.as_view()),
     path('orders/<str:order_item_id>/', views.GetOrderData.as_view()),
     path('refunds/', views.GetRefundsData.as_view()),
     path("sp-api/estimated-fees/", views.GetEstimatedItemFees.as_view()),
     path("sp-api/listing-details/", views.GetListingDetails.as_view()),
     path("sp-api/item-eligibility/", views.GetItemEligibility.as_view())
]