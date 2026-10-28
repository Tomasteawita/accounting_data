from django.shortcuts import render


def home(request):
    """Renderiza la vista raíz (Home) vacía bajo los lineamientos visuales del sistema."""
    return render(request, "app/home.html")
