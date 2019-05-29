import re
import time
from urllib.parse import urlparse

from celery.result import AsyncResult
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from rest_framework.authtoken.models import Token
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers import LogSerializer
from django_logs.consts import types, rowboat_types
from django_logs.models import Log
from django_logs.parser import LogParser
from django_logs.utils import get_expiry, request_url


# Create your views here.
class LogView(APIView):
    """
    get:
    Return a list of logs currently owned by the user. If `short_code` is specified, grabs the data for a specific log.
    """

    permission_classes = [IsAuthenticated, ]

    def get(self, request, short_code=None):
        logs = Log.objects.filter(author=request.user, short_code=short_code) if short_code else \
            Log.objects.filter(author=request.user)
        serializer = LogSerializer(logs, many=True)
        return Response(serializer.data)


class LogCreate(APIView):
    """
    post:
    Creates a new log.
    """

    permission_classes = [IsAuthenticated, ]

    def post(self, request, **kwargs):
        if kwargs:
            resp = {'detail': 'POSTing to a log is not allowed!'}
            return Response(resp, status=405)
        t = time.time()
        data = request.POST
        if not all([any([any(['url', 'content']) in data, request.FILES is not None]), 'type' in data]):
            resp = {'detail': 'Request body must contain one of [files, url, content] and [type] to parse!'}
            return Response(resp, status=400)

        if data.get('type') not in types:
            resp = {'detail': f'Log type must be one of [{", ".join(types.keys())}]!'}
            return Response(resp, status=400)

        variant = None
        if data.get('url'):
            url = data.get('url')
            resp = request_url(url)
            if not resp:
                resp = {'detail': f'Connection to url "{url}" failed.'}
                return Response(resp, status=400)

            if 'text/plain' not in resp.headers['Content-Type']:
                resp = {'detail': f'Content-Type of "{url}" must be of type "text/plain"!'}
                return Response(resp, status=400)

            origin = ('url', url)
            variant = rowboat_types.get(urlparse(url).netloc)
            try:
                content = resp.content.decode()
            except UnicodeDecodeError:
                resp = {'detail': 'Request content must be of encoding utf-8!'}
                return Response(resp, status=400)

        elif data.get('content'):
            origin = 'raw'
            content = data.get('content')
        elif request.FILES:
            origin = 'file'
            with request.FILES[next(iter(request.FILES))].open() as f:
                content = f.read()
        else:  # Nothing to parse, we've given up
            resp = {'detail': 'Request body must contain one of [files, url, content] and [type] to parse!'}
            return Response(resp, status=400)

        if not content:
            resp = {'detail': 'Log content must not be empty!'}
            return Response(resp, status=400)

        log_type = data.get('type')
        new = data.get('new')
        match_len = len(re.findall(types[log_type], content, re.MULTILINE))
        author = request.user if request.user.is_authenticated else None
        expires = get_expiry(data)
        if not expires:
            resp = {'detail': f'Expiry time must not exceed two weeks, or {60 * 60 * 24 * 7 * 2}!'}
            return Response(resp, status=400)

        if match_len > 0:
            content = re.sub('\r\n', '\n', content)
            short, created = LogParser(log_type, content, origin=origin, variant=variant).create(
                author, expires=expires, new=new)
            data = {
                'short': short,
                'url': f'http{"s" if request.is_secure() else ""}://{request.META["HTTP_HOST"]}/{short}',
                'created': created,
                'time': time.time() - t
            }
            return Response(data, status=201 if created else 200)

        resp = {'detail': 'Could not parse log content using specified type!'}
        return Response(resp, status=400)


class LogDestroy(APIView):
    """
    delete:
    Deletes a log, specified with `short_code`.
    """

    permission_classes = [IsAuthenticated, ]

    def delete(self, request, short_code):
        log = get_object_or_404(Log.objects.all(), author=request.user, short_code=short_code)
        log.delete()
        return Response({'detail': f'Log {short_code} has been deleted.'})


@user_passes_test(lambda u: u.is_superuser)
def traceback(request):
    t = request.GET.get('t')
    tasks = t.split(',')
    gathered = []
    for task in tasks:
        t = AsyncResult(id=task)
        gathered.append({'id': t.id, 'status': t.status, 'result': t.result if not isinstance(
            t.result, Exception) else None, 'traceback': t.traceback})
    return JsonResponse(gathered, safe=False)


def get_token(request):
    if not request.user.is_authenticated:
        return JsonResponse(data={'detail': '401: Unauthorized'}, status=401)
    token, created = Token.objects.update_or_create(user=request.user)
    return JsonResponse(data={'token': token.key}, status=201 if created else 200)