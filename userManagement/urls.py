from django.urls import path
from . import views

app_name = 'userManagement'

urlpatterns = [
    path('home/', views.HomeView.as_view(), name='home'),
    path('', views.UserListView.as_view(), name='user_list'),
    path('<int:pk>/role/', views.UserRoleUpdateView.as_view(), name='user_role'),
    path('invite/', views.InviteView.as_view(), name='invite'),
    path('accept/<uuid:token>/', views.AcceptInviteView.as_view(), name='accept_invite'),
    path('<int:pk>/reinitialisation/', views.PasswordResetLinkView.as_view(), name='password_reset_link'),
    path('reinitialiser/<uidb64>/<token>/', views.PasswordResetView.as_view(), name='password_reset'),
    path('password/', views.ChangePasswordView.as_view(), name='change_password'),
    path('<int:pk>/delete/', views.UserDeleteView.as_view(), name='user_delete'),
]
