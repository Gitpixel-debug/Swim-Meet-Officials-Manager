# myapp/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path("login", views.login_view, name="login"),
    path("logout", views.logout_view, name="logout"),
    path("register", views.register, name="register"),
    
    # Officials (separate login flow)
    # official login/register removed; use main referee login/register
    path("official/dashboard", views.official_dashboard, name="official-dashboard"),
    # Backwards-compatible aliases to main auth views (official-specific routes removed)
    path("official/register", views.register, name="official-register"),
    path("official/login", views.login_view, name="official-login"),
    path("official/join", views.join_meet, name="join-meet"),
    path("official/join_session/<int:session_id>", views.join_session, name="join-session"),
    path("official/join_meet/<int:meet_id>", views.join_sessions_from_meet, name="join-sessions-from-meet"),
    path('auth/request_code/', views.request_login_code, name='request-login-code'),
    path('auth/verify_code/', views.verify_login_code, name='verify-login-code'),
    path("official/leave/<int:assignment_id>", views.leave_session, name="leave-session"),

    # Referee dashboard: shows meets created by the logged-in referee
    path("referee/dashboard", views.referee_dashboard, name="referee-dashboard"),

    path("meet/create", views.meet_create, name="meet-create"),
    path("meet/<int:meet_id>", views.meet_home, name="meet-home"),
    path('meet/<int:meet_id>/add_session/', views.add_session, name='add-session'),
    path('session/<int:session_id>/delete/', views.delete_session, name='delete-session'),
    path("session/<int:session_id>", views.session_home, name="session-home"),
    path('edit_session/<int:session_id>/', views.edit_session, name='edit_session'),
    path('upload_officials/', views.upload_officials, name='upload_officials'),
    path('session/<int:session_id>/send_join/<int:assignment_id>/', views.send_join_code_view, name='send-join-code'),
    path('session/<int:session_id>/delete_csv/', views.delete_session_csv, name='delete-session-csv'),
    path('check_in/<int:assignment_id>/', views.check_in, name='check-in'),
    path('session/<int:session_id>/self_check_in/', views.self_check_in, name='self-check-in'),
    path('session/<int:session_id>/send_join_all/', views.send_join_all, name='send-join-all'),
    path('session/<int:session_id>/deck/', views.deck_assignments, name='deck-assignments'),

]