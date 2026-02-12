from django.urls import path

from . import views

urlpatterns = [
    path('', views.matchup, name='matchup'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
]
