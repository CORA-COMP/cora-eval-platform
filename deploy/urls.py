"""Root URL conf: the core routes plus CORA-COMP's own pages.

The core shell is shared with the other competitions, so anything specific to this one
(the results view) is mounted here rather than added to it.
"""
from django.urls import include, path

from comp_eval_platform.urls import urlpatterns as core_urlpatterns

#: Under ``/api/`` because that is the prefix the frontend dev server proxies to the
#: backend (as the branding assets already do), so one URL works both behind the Vite
#: proxy and in a deployment.
urlpatterns = core_urlpatterns + [
    path("api/cora/", include("cora_comp.urls")),
]
