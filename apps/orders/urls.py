from django.urls import path
from .views import (
    CreateServiceOrderView,
    UpdateServiceOrderView,           
    SellerUpdateServiceOrderView,     
    DeleteServiceOrderView,
    OrdersListView,
    SellerOrderListView,
    AcceptOrderView,
)

urlpatterns = [
    # Buyer actions
    path('<slug:buyer_slug>/orders/create/', CreateServiceOrderView.as_view(), name='order-create'),
    path('<slug:buyer_slug>/orders/<str:id>/update/', UpdateServiceOrderView.as_view(), name='order-update'), 
    path('<slug:buyer_slug>/orders/<str:id>/delete/', DeleteServiceOrderView.as_view(), name='order-delete'),
    path('<slug:buyer_slug>/orders/', OrdersListView.as_view(), name='buyer-orders'),

    # Seller actions
    path('<slug:seller_slug>/orders/seller/', SellerOrderListView.as_view(), name='seller-orders'),
    path('<slug:seller_slug>/orders/<str:id>/accept/', AcceptOrderView.as_view(), name='order-accept'),
    path('<slug:seller_slug>/orders/<str:id>/seller-update/', SellerUpdateServiceOrderView.as_view(), name='seller-order-update'), 
]
