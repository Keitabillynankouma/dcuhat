from django.urls import path

from . import views

urlpatterns = [
    path("search/", views.SearchView.as_view(), name="search"),
    path("search/suggest/", views.SuggestView.as_view(), name="search-suggest"),
]
