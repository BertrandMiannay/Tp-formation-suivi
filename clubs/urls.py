from django.urls import path

from . import views

urlpatterns = [
    path('choisir/', views.club_choose, name='club-choose'),
]
