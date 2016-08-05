import json

from django.http import HttpResponseBadRequest, JsonResponse
from django.contrib.auth.models import User

from rest_framework import renderers, viewsets,filters,permissions

from .models import Silo, LabelValueStore
from .serializers import *
from silo.permissions import IsOwnerOrReadOnly
from django.contrib.auth.models import User
from rest_framework.decorators import detail_route, list_route
from rest_framework import pagination


import django_filters

def silo_data_api(request, id):
    if id <= 0:
        return HttpResponseBadRequest("The silo_id = %s is invalid" % id)

    data = LabelValueStore.objects(silo_id=id).to_json()
    json_data = json.loads(data)
    return JsonResponse(json_data, safe=False)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

class PublicSiloViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PublicSiloSerializer

    def get_queryset(self):
        return Silo.objects.filter(public=True)

    @detail_route()
    def data(self, request, id):
        if id <= 0:
            return HttpResponseBadRequest("The silo_id = %s is invalid" % id)
        data = LabelValueStore.objects(silo_id=id).to_json()
        json_data = json.loads(data)
        return JsonResponse(json_data, safe=False)

class SiloViewSet(viewsets.ModelViewSet):
    """
    This viewset automatically provides `list`, `create`, `retrieve`,
    `update` and `destroy` actions.
    """
    serializer_class = SiloSerializer
    lookup_field = 'id'
    # this permission sets seems to break the default permissions set by the restframework
    #permission_classes = (permissions.IsAuthenticatedOrReadOnly,
    #                      IsOwnerOrReadOnly,)
    filter_fields = ('owner__username','shared__username','id','tags','public')
    filter_backends = (filters.DjangoFilterBackend,)

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            #pagination.PageNumberPagination.page_size = 200
            return Silo.objects.all()
        return Silo.objects.filter(owner=user)

    @detail_route()
    def data(self, request, id):
        if id <= 0:
            return HttpResponseBadRequest("The silo_id = %s is invalid" % id)

        data = LabelValueStore.objects(silo_id=id).to_json()
        json_data = json.loads(data)
        return JsonResponse(json_data, safe=False)


class TagViewSet(viewsets.ModelViewSet):
    """
    This viewset automatically provides `list`, `create`, `retrieve`,
    `update` and `destroy` actions.
    """
    queryset = Tag.objects.all()
    serializer_class = TagSerializer


class ReadViewSet(viewsets.ModelViewSet):
    """
    This viewset automatically provides `list`, `create`, `retrieve`,
    `update` and `destroy` actions.
    """
    queryset = Read.objects.all()
    serializer_class = ReadSerializer

class ReadTypeViewSet(viewsets.ModelViewSet):
    """
    This viewset automatically provides `list`, `create`, `retrieve`,
    `update` and `destroy` actions.
    """
    queryset = ReadType.objects.all()
    serializer_class = ReadTypeSerializer
