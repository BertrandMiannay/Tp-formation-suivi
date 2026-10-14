from django.urls import path

from . import views

urlpatterns = [
    path('choisir/', views.club_choose, name='club-choose'),
    # Gestion des clubs (super-admin)
    path('', views.club_list, name='club-list'),
    path('nouveau/', views.club_create, name='club-create'),
    path('<int:pk>/', views.club_detail, name='club-detail'),
    path('<int:pk>/supprimer/', views.club_delete, name='club-delete'),
]
