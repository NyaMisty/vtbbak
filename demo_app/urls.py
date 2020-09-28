from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('start', views.start_user, name='start'),
]