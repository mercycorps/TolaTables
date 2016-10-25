import json

from django.http import HttpResponseBadRequest, JsonResponse, HttpResponse
from django.contrib.auth.models import User

from rest_framework import renderers, viewsets,filters,permissions

from .models import Silo, LabelValueStore
from .serializers import *
from silo.permissions import IsOwnerOrReadOnly
from django.contrib.auth.models import User
from rest_framework.decorators import detail_route, list_route
from rest_framework import pagination


import django_filters

"""
def silo_data_api(request, id):
    if id <= 0:
        return HttpResponseBadRequest("The silo_id = %s is invalid" % id)

    data = LabelValueStore.objects(silo_id=id).to_json()
    json_data = json.loads(data)
    return JsonResponse(json_data, safe=False)
"""

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

class PublicSiloViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PublicSiloSerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,
                          IsOwnerOrReadOnly,)
    lookup_field = 'id'

    def get_queryset(self):
        return Silo.objects.filter(public=True)

    @detail_route()
    def data(self, request, id):
        if id <= 0:
            return HttpResponseBadRequest("The silo_id = %s is invalid" % id)

        silo = Silo.objects.get(pk=id)
        if silo.public == False:
            return HttpResponse("This table is not public. You must use the private API.")
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
    permission_classes = (IsOwnerOrReadOnly,)
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

        draw = int(request.GET.get("draw", 1))
        offset = int(request.GET.get('start', -1))
        length = int(request.GET.get('length', 10))
        recordsTotal = LabelValueStore.objects(silo_id=id).count()

        #print("offset=%s length=%s" % (offset, length))
        #page_size = 100
        #page = int(request.GET.get('page', 1))
        #offset = (page - 1) * page_size
        #if page > 0:
        # workaround until the problem of javascript not increasing the value of length is fixed
        if offset >= 0:
            length = offset + length
            data = LabelValueStore.objects(silo_id=id).exclude('create_date', 'edit_date', 'silo_id').skip(offset).limit(length).to_json()
        else:
            data = LabelValueStore.objects(silo_id=id).exclude('create_date', 'edit_date', 'silo_id').to_json()
        json_data = json.loads(data)

        return JsonResponse({"data": json_data, "draw": draw, "recordsTotal": recordsTotal, "recordsFiltered": recordsTotal}, safe=False)


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
