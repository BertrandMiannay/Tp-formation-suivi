from django.urls import path

from . import views

# Administration : /gestion/
urlpatterns = [
    path('', views.season_gestion, name='saison-gestion'),
    path('set-current/<int:pk>/', views.set_current_season, name='saison-set-current'),
    path('delete/<int:pk>/', views.delete_season, name='saison-delete'),
    path('cursus/', views.cursus_list, name='saison-cursus'),
    path('cursus/creer/', views.cursus_create, name='saison-cursus-creer'),
    path('cursus/importer/', views.cursus_import_json, name='saison-cursus-importer'),
    path('cursus/<int:pk>/', views.cursus_detail, name='saison-cursus-detail'),
    path('cursus/<int:pk>/archiver/', views.cursus_archive, name='saison-cursus-archiver'),
]

# Formations et inscriptions : /formations/
formation_urlpatterns = [
    path('', views.formation_list, name='formation-list'),
    path('creer/', views.formation_create, name='formation-create'),
    path('<int:pk>/', views.formation_detail, name='formation-detail'),
]

# Élèves : /eleves/
student_urlpatterns = [
    path('nouveau/', views.student_create, name='eleve-create'),
    path('<int:pk>/modifier/', views.student_edit, name='eleve-edit'),
    path('<int:pk>/evaluation/', views.evaluation, name='eleve-evaluation'),
    path('<int:pk>/evaluation/<int:cursus_pk>/', views.evaluation_save, name='eleve-evaluation-save'),
    path('<int:pk>/evaluation/<int:cursus_pk>/export/', views.evaluation_export, name='eleve-evaluation-export'),
    path('<int:pk>/evaluation/historique/<int:ev_pk>/supprimer/', views.evaluation_delete, name='eleve-evaluation-delete'),
]
