"""The results view — CORA-COMP's own page, served by the plugin rather than the shell.

The core frontend is shared with the other competitions, so a page that only makes sense
here lives here: one server-rendered template plus the JSON it reads. It is reached from
the landing page's links (see ``competition.py``).
"""
from django.http import JsonResponse
from django.shortcuts import render

from .plots import plot_payload


def results_page(request):
    """The page itself. It fetches ``results_data`` on load and does the rest client-side,
    so the selectors and the prepare-time toggle redraw without a round trip."""
    return render(request, "cora_comp/results.html", {
        "authenticated": request.user.is_authenticated,
    })


def results_data(request):
    """Every measured instance, with the facet values to filter it by."""
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=403)
    return JsonResponse(plot_payload())
