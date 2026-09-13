from django.urls import path
from django.http import JsonResponse
from datetime import datetime

def health(request):
    return JsonResponse({'status': 'ok', 'timestamp': datetime.now().isoformat()})

urlpatterns = [
    path('', health),
]
