import json

from django.http import HttpResponseBadRequest, JsonResponse, HttpResponse
from django.contrib.auth.models import User
from django.db.models import Q

from rest_framework import renderers, viewsets,filters,permissions

from .models import Silo, LabelValueStore, Country, WorkflowLevel1, WorkflowLevel2
from .serializers import *
from silo.permissions import *
from django.contrib.auth.models import User
from rest_framework.decorators import detail_route, list_route
from rest_framework.permissions import IsAuthenticated
from rest_framework import pagination
from rest_framework.views import APIView
from rest_framework_json_api.parsers import JSONParser
from rest_framework_json_api.renderers import JSONRenderer

from django_filters.rest_framework import DjangoFilterBackend
import django_filters

from tola.util import getSiloColumnNames, getCompleteSiloColumnNames


import django_filters

"""
def silo_data_api(request, id):
    if id <= 0:
        return HttpResponseBadRequest("The silo_id = %s is invalid" % id)

    data = LabelValueStore.objects(silo_id=id).to_json()
    json_data = json.loads(data)
    return JsonResponse(json_data, safe=False)
"""


class OrganizationViewSet(viewsets.ModelViewSet):
    filter_fields = ('name',)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

class UserViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = User.objects.all()
    serializer_class = UserSerializer


class CountryViewSet(viewsets.ModelViewSet):
    filter_fields = ('country',)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    queryset = Country.objects.all()
    serializer_class = CountrySerializer


class WorkflowLevel1ViewSet(viewsets.ModelViewSet):
    filter_fields = ('name',)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    queryset = WorkflowLevel1.objects.all()
    serializer_class = WorkflowLevel1Serializer


class WorkflowLevel2ViewSet(viewsets.ModelViewSet):
    filter_fields = ('name','workflowlevel1__name')
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    queryset = WorkflowLevel2.objects.all()
    serializer_class = WorkflowLevel2Serializer


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
        query = request.GET.get('query',"{}")
        filter_fields = json.loads(query)

        shown_cols = set(json.loads(request.GET.get('shown_cols',json.dumps(getSiloColumnNames(id)))))


        recordsTotal = LabelValueStore.objects(silo_id=id, **filter_fields).count()


        #print("offset=%s length=%s" % (offset, length))
        #page_size = 100
        #page = int(request.GET.get('page', 1))
        #offset = (page - 1) * page_size
        #if page > 0:
        # workaround until the problem of javascript not increasing the value of length is fixed
        data = LabelValueStore.objects(silo_id=id, **filter_fields).exclude('create_date', 'edit_date', 'silo_id','read_id')

        for col in getCompleteSiloColumnNames(id):
            if col not in shown_cols:
                data = data.exclude(col)

        sort = str(request.GET.get('sort',''))
        data = data.order_by(sort)
        json_data = json.loads(data.to_json())
        return JsonResponse(json_data, safe=False)


class SilosByUser(viewsets.ReadOnlyModelViewSet):
    """
    Lists all silos by a user; returns data in a format
    understood by Ember DataStore.
    """
    serializer_class = SiloSerializer
    parser_classes = (JSONParser,)
    renderer_classes = (JSONRenderer,)

    def get_queryset(self):
        silos = Silo.objects.all()
        user_id = self.request.query_params.get("user_id", None)
        if user_id:
            silos = silos.filter(owner__id=user_id)
        return silos


class SiloViewSet(viewsets.ReadOnlyModelViewSet):
    """
    This viewset automatically provides `list` and `retrieve` actions.
    """
    serializer_class = SiloSerializer
    lookup_field = 'id'
    # this permission sets seems to break the default permissions set by the restframework
    # permission_classes = (IsOwnerOrReadOnly,)
    permission_classes = (IsAuthenticated, Silo_IsOwnerOrCanRead,)
    filter_fields = ('owner__username','shared__username','id','tags','public')
    filter_backends = (filters.DjangoFilterBackend,)

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            #pagination.PageNumberPagination.page_size = 200
            return Silo.objects.all()

        return Silo.objects.filter(
            Q(owner=user) | Q(public=True) | Q(shared=self.request.user)
            ).distinct()


    @detail_route()
    def data(self, request, id):
        # calling get_object applies the permission classes to this query
        silo = self.get_object()

        draw = int(request.GET.get("draw", 1))
        offset = int(request.GET.get('start', -1))
        length = int(request.GET.get('length', 10))
        #filtering syntax is the mongodb syntax
        query = request.GET.get('query',"{}")
        filter_fields = json.loads(query)

        recordsTotal = LabelValueStore.objects(silo_id=id, **filter_fields).count()


        #print("offset=%s length=%s" % (offset, length))
        #page_size = 100
        #page = int(request.GET.get('page', 1))
        #offset = (page - 1) * page_size
        #if page > 0:
        # workaround until the problem of javascript not increasing the value of length is fixed
        if offset >= 0:
            length = offset + length
            data = LabelValueStore.objects(silo_id=id, **filter_fields).exclude('create_date', 'edit_date', 'silo_id','read_id').skip(offset).limit(length)
        else:
            data = LabelValueStore.objects(silo_id=id, **filter_fields).exclude('create_date', 'edit_date', 'silo_id','read_id')

        sort = str(request.GET.get('sort',''))
        data = data.order_by(sort)
        json_data = json.loads(data.to_json())

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
    This viewset automatically provides `list` and `retrieve`, actions.
    """
    serializer_class = ReadSerializer
    permission_classes = (IsAuthenticated, Read_IsOwnerViewOrWrite,)

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Read.objects.all()

        return Read.objects.filter(
            Q(owner=user) |
            Q(silos__public=True) |
            Q(silos__shared=self.request.user)
        ).distinct()


class ReadTypeViewSet(viewsets.ModelViewSet):
    """
    This viewset automatically provides `list`, `create`, `retrieve`,
    `update` and `destroy` actions.
    """
    queryset = ReadType.objects.all()
    serializer_class = ReadTypeSerializer


#####-------API Views to Feed Data to Tolawork API requests-----####
'''
    This view responds to the 'GET' request from TolaWork
'''
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response


@api_view(['GET'])
@authentication_classes(())
@permission_classes(())

def tables_api_view(request):
    """
   Get TolaTables Tables owned by a user logged in Tolawork & a list of logged in Users,
    """
    if request.method == 'GET':
        user = request.GET.get('email')

        user_id = User.objects.get(email=user).id

        tables = Silo.objects.filter(owner=user_id).order_by('-create_date')
        table_logged_users = logged_in_users()

        table_serializer = SiloModelSerializer(tables, many=True)
        user_serializer = LoggedUserSerializer(table_logged_users, many=True)

        users = user_serializer.data
        tables = table_serializer.data


        tables_data = {'tables':tables, 'table_logged_users': users}


        return Response(tables_data)

#return users logged into TolaActivity
def logged_in_users():

    logged_users = {}

    logged_users = LoggedUser.objects.order_by('username')
    for logged_user in logged_users:
        logged_user.queue = 'TolaTables'

    return logged_users
