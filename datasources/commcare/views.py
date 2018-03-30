import json
import requests
import urllib
import base64

from requests.auth import HTTPDigestAuth

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse, reverse_lazy
from django.http import HttpResponseRedirect, HttpResponseBadRequest, \
    HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.datastructures import MultiValueDictKeyError

from silo.models import Silo, Read, ReadType, ThirdPartyTokens
from tola.util import saveDataToSilo, getSiloColumnNames
from commcare.forms import CommCareAuthForm, CommCareProjectForm
from commcare.tasks import fetchCommCareData, requestCommCareData
from commcare.util import getCommCareDataHelper, getCommCareReportIDs, \
    getCommCareRecordCount

@login_required
def getCommCareAuth(request):
    """
    Get the forms owned or shared with the logged in user
    :param request:
    :return: list of Ona forms paired with action buttons
    """
    provider = 'CommCare'

    if request.method == 'POST':

        form = CommCareAuthForm(request.POST)
        if form.is_valid():
            # test validity of token by trying to grab some data
            ping_url = 'https://www.commcarehq.org/a/%s/api/v0.5/case/?limit=1' \
                % request.POST['project']
            headers = {'Authorization': 'ApiKey %(u)s:%(a)s' % {
                    'u' : request.POST['username'],
                    'a' : request.POST['auth_token']
                }
            }
            response = requests.get(ping_url, headers=headers)
            if response.status_code == 401:
                messages.error(
                    request,
                    "Invalid username, authorization token or project."
                )
                form = CommCareAuthForm()
            elif response.status_code == 200:
                commcare_token = ThirdPartyTokens(
                    name = provider,
                    user_id = request.user.id,
                    token = request.POST['auth_token'],
                    username = request.POST['username']
                )
                commcare_token.save()
                redirect_url = reverse('getCommCareData') + \
                    '?project=%s' % request.POST['project']
                return redirect(redirect_url)
        else:
            messages.error(request, "You have invalid values in your form. \
                Please try again.")
            return render(request, 'getCommCareAuth', {'form': form})

    else:
        try:
            #look for authorization token
            commcare_token = ThirdPartyTokens.objects.get(
                user=request.user, name=provider
            )
            return redirect('getCommCareData')

        # Catch an issue where there is more than one token in the DB.
        # This should never happen, but just in case.
        except ThirdPartyTokens.MultipleObjectsReturned:
            messages.error(request,
                "There was a problem with your login.  \
                Please re-enter your information.")
            form = CommCareAuthForm()
        except ThirdPartyTokens.DoesNotExist:
            form = CommCareAuthForm()

        return render(request, 'getcommcareforms.html', {'form': form})

    return render(request, 'getcommcareforms.html', {'form': form})

@login_required
def getCommCareData(request):
    """
    Get the forms owned or shared with the logged in user
    :param request:
    :return: list of Ona forms paired with action buttons
    """

    provider = "CommCare"

    #get silo choices for the dropdown
    silos = Silo.objects.filter(owner=request.user)
    silo_choices = [(0, ""), (-1, "Create a new Table")]
    for silo in silos:
        silo_choices.append((silo.pk, silo.name))

    user_id = request.user.id

    # If the token can't be retrieved, redirect them to the auth page.
    try:
        commcare_token = ThirdPartyTokens.objects.get(
            user_id=request.user, name='CommCare'
        )
    except (ThirdPartyTokens.MultipleObjectsReturned,
            ThirdPartyTokens.DoesNotExist
    ):
        return redirect('getCommCareAuth')


    if request.method == 'POST':

        silo_id = int(request.POST.get("silo", None))
        if silo_id in [-1 ,0]:
            silo_id = None

        auth_header = {'Authorization': 'ApiKey %(u)s:%(a)s' % \
            {'u' : commcare_token.username, 'a' : commcare_token.token}}
        project = request.POST['project']
        report_choices = [('default', 'Select a Report')]
        try:
            report_id = request.POST['commcare_report_name']
            report_map = getCommCareReportIDs(project, auth_header)
            report_choices.extend([(k, v) for k,v in report_map.iteritems()])
        except KeyError:
            report_id = False
        try:
            commcare_form_id = request.POST['commcare_form_name']
        except KeyError:
            commcare_form_id = False

        form = CommCareProjectForm(
            request.POST, silo_choices=silo_choices,
            report_choices=report_choices, user_id=user_id
        )

        if form.is_valid():

            if report_id != 'default':
                report_name = report_map[report_id]
            else:
                report_name = None

            user = request.user
            download_type = request.POST['download_type']
            base_url = 'https://www.commcarehq.org/a/%s/api/v0.5/%s/'

            #set url and get size of dataset
            if download_type == 'commcare_report':
                url = base_url % (project, 'configurablereportdata')
                url = url + report_id + '/?format=JSON&limit=1'
                data_count = getCommCareRecordCount(
                    url, auth_header, project, report_id
                )
            elif download_type == 'commcare_form':
                url = base_url % (project, 'form')
                url = url + '?limit=1'
                data_count = getCommCareRecordCount(url, auth_header)
            else:
                url = base_url % (project, 'case')
                url = url + '?format=JSON&limit=1'
                data_count = getCommCareRecordCount(url, auth_header)

            if download_type == 'commcare_report':
                read_name = '%s report - %s' % (project, report_name)
            elif download_type == 'commcare_form':
                read_name = '%s form - %s' % (project, report_name)
            else:
                read_name = project + ' cases'
            read = Read.objects.create(
                read_name=read_name, owner=user, read_url=url,
                type=ReadType.objects.get(read_type=provider),
                description=""
            )
            requested_silo_name = request.POST.get('new_table_name', None)
            silo, silo_created = Silo.objects.get_or_create(id=silo_id, defaults={"name": requested_silo_name, "public": False, "owner": request.user})
            if silo_created:
                silo.reads.add(read)
            elif read not in silo.reads.all():
                silo.reads.add(read)

            #get the actual data
            extra_data = report_name or commcare_form_id
            ret = getCommCareDataHelper(url, auth_header, True, data_count, silo, read, download_type, extra_data, update=False)
            messages.add_message(request,ret[0],ret[1])
            #need to impliment if import faluire
            cols = ret[2]
            return HttpResponseRedirect(reverse_lazy("siloDetail", kwargs={'silo_id' : silo.id}))

        # Need to implement some sort of error catching code here.  CommCare
        # sometimes returns html error messages to API calls
        # else:
        #     for m in messages.get_messages(request):
        #         print 'm e ss', m
        #     messages.error(request, "Could not get data")
        return render(request, 'getcommcareforms.html',
                        {'form': form, 'auth': 'authenticated'})

    else:
        user_id = request.user.id
        form = CommCareProjectForm(
            user_id = user_id,
            silo_choices = silo_choices,
        )
        try:
            form.fields['project'].initial = request.GET.get('project')
        except:
            pass

        return render(request, 'getcommcareforms.html',
                        {'form': form, 'auth': 'authenticated'})


@login_required
def commcareLogout(request):
    try:
        token = ThirdPartyTokens.objects.get(user=request.user, name="CommCare")
        token.delete()
    except Exception as e:
        pass

    messages.error(request, "You have been logged out of your CommCare account.  Any Tables you have created with this account ARE still available, but you must log back in here to update them.")
    return HttpResponseRedirect(reverse_lazy('getCommCareAuth'))


@login_required
def get_commcare_report_names(request):

    project = request.GET['project']
    commcare_token = ThirdPartyTokens.objects.get(user=request.user, name='CommCare')
    auth_header = {'Authorization': 'ApiKey %(u)s:%(a)s' % \
        {'u' : commcare_token.username, 'a' : commcare_token.token}}
    reports = getCommCareReportIDs(project, auth_header)
    return HttpResponse(json.dumps(reports))
