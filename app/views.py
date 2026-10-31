from django.shortcuts import render


def home(request):
    """Renderiza la Landing Page (app/home.html) directamente sin realizar consultas a PostgreSQL."""
    return render(request, "app/home.html")
