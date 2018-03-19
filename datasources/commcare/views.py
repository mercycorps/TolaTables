import json
import requests
import urllib
import base64

from requests.auth import HTTPDigestAuth
from django.http import HttpResponseRedirect, HttpResponseBadRequest, HttpResponse


from tola.util import saveDataToSilo, getSiloColumnNames
from django.shortcuts import redirect, render
from django.core.urlresolvers import reverse, reverse_lazy

from django.contrib import messages
from django.utils import timezone
from django.utils.datastructures import MultiValueDictKeyError
from django.contrib.auth.decorators import login_required

from silo.models import Silo, Read, ReadType, ThirdPartyTokens
from .forms import CommCareAuthForm, CommCareProjectForm
from .tasks import fetchCommCareData, requestCommCareData
from .util import getCommCareCaseData, getCommCareReportIDs

@login_required
def getCommCareAuth(request):
    """
    Get the forms owned or shared with the logged in user
    :param request:
    :return: list of Ona forms paired with action buttons
    """
    provider = 'CommCare'

    if request.method == 'POST':
        #their exists a project and authorization so get the data
        form = CommCareAuthForm(request.POST)

        if form.is_valid():
            # test validity of token by trying to grab some data
            ping_url = 'https://www.commcarehq.org/a/%s/api/v0.5/case/?limit=1' % request.POST['project']
            headers = {'Authorization': 'ApiKey %(u)s:%(a)s' % \
                {'u' : request.POST['username'], 'a' : request.POST['auth_token']}}
            response = requests.get(ping_url, headers=headers)
            if response.status_code == 401:
                messages.error(request, "Invalid username, authorization token or project.")
                form = CommCareAuthForm()
            elif response.status_code == 200:
                print 'req post', request.POST
                commcare_token = ThirdPartyTokens(
                    name = provider,
                    user_id = request.user.id,
                    token = request.POST['auth_token'],
                    username = request.POST['username']
                )
                commcare_token.save()
                redirect_url = reverse('getCommCareData') + '?project=%s' % request.POST['project']
                print 'rdirurl', redirect_url
                return redirect(redirect_url)
        else:
            messages.error(request, "You have invalid values in your form. Please try again.")
            return render(request, 'getCommCareAuth', {'form': form})

    else:
        try:
            #look for authorization token
            commcare_token = ThirdPartyTokens.objects.get(user=request.user,name=provider)
            return redirect('getCommCareData')

        #Catch an issue where there is more than one token in the DB.  This should never happen, but just in case.
        except ThirdPartyTokens.MultipleObjectsReturned:
            messages.error(request, "There was a problem with your login.  Please re-enter your information.")
            form = CommCareAuthForm()
        except ThirdPartyTokens.DoesNotExist:
            form = CommCareAuthForm()

        return render(request, 'getcommcareforms.html', {'form': form})

            # try:
            #     created = False
            #     #either add a new commcare_auth token or retrieve an old one
    #             try:
    #                 if request.POST['auth_token'] != '':
    #                     commcare_token, created = ThirdPartyTokens.objects.get_or_create(user=request.user,name=provider,token=request.POST['auth_token'],username=request.POST['username'])
    #                     form = CommCareAuthForm(request.POST, choices=silo_choices, user_id=user_id)
    #                     if form.is_valid():
    #                         pass
    #             except Exception as e:
    #                 commcare_token = ThirdPartyTokens.objects.get(user=request.user,name=provider)
    #
    #             project = request.POST['project']
    #             if request.POST['download_type'] == 'commcare_form':
    #                 download_type = 'form'
    #                 url_params = {}
    #             else:
    #                 download_type = 'case'
    #                 url_params = {'format': 'JSON'}
    #             url_params['limit'] = 1
    #             #https://www.commcarehq.org/a/[PROJECT]/api/v0.5/simplereportconfiguration/?format=json
    #
    #             url = 'https://www.commcarehq.org/a/{project}/api/v0.5/{type}/?{params}'
    #             url = url.format(
    #                 project=project,
    #                 type=download_type,
    #                 params=urllib.urlencode(url_params)
    #             )
    #             headers = {'Authorization': 'ApiKey %(u)s:%(a)s' % {'u' : commcare_token.username, 'a' : commcare_token.token}}
    #             response = requests.get(url, headers=headers)
    #             if response.status_code == 401:
    #                 messages.error(request, "Invalid username, authorization token or project.")
    #                 try:
    #                     token = ThirdPartyTokens.objects.get(user=request.user, name="CommCare")
    #                     token.delete()
    #                 except Exception as e:
    #                     pass
    #                 form = CommCareAuthForm(choices=silo_choices, user_id=user_id)
    #             elif response.status_code == 200:
    #                 response_data = json.loads(response.content)
    #                 total_cases = response_data.get('meta').get('total_count')
    #                 if created: commcare_token.save()
    #                 #add the silo and reads if necessary
    #                 try:
    #                     silo_id = int(request.POST.get("silo", None))
    #                     if silo_id == 0:
    #                         silo_id = None
    #                 except Exception as e:
    #                     return HttpResponse("Silo ID can only be an integer")
    #
    #                 #get the actual data
    #                 authorization = {'Authorization': 'ApiKey %(u)s:%(a)s' % {'u' : commcare_token.username, 'a' : commcare_token.token}}
    #
    #                 return HttpResponseRedirect(reverse_lazy("siloDetail", kwargs={'silo_id' : silo.id}))
    #
    #             else:
    #                 messages.error(request, "A %s error has occured: " % (response.status_code))
    #                 form = CommCareAuthForm(choices=silo_choices, user_id=user_id)
    #         except KeyboardInterrupt as e:
    #             form = CommCareAuthForm(request.POST, choices=silo_choices, user_id=user_id)
    #             form.is_valid()
    #     else:
    #         try:
    #             #look for authorization token
    #             commcare_token = ThirdPartyTokens.objects.get(user=request.user,name=provider)
    #         except Exception as e:
    #             form = CommCareAuthForm(request.POST, choices=silo_choices, user_id=user_id)
    #
    # else:
    #     try:
    #         #look for authorization token
    #         commcare_token = ThirdPartyTokens.objects.get(user=request.user,name=provider)
    #         form = CommCareProjectForm(choices=silo_choices, user_id=user_id)
    #         auth = 0
    #     except Exception as e:
    #         form = CommCareAuthForm(choices=silo_choices, user_id=user_id)

    # return render(request, 'getcommcareforms.html', {'form': form, 'auth': auth, 'entries': total_cases, 'time' : timezone.now()})

    return render(request, 'getcommcareforms.html', {'form': form})

@login_required
def getCommCareData(request):
    """
    Get the forms owned or shared with the logged in user
    :param request:
    :return: list of Ona forms paired with action buttons
    """

    # TODO:  probably need to permit users to have multiple tokens, but with unique combo of username and provider

    provider = "CommCare"

    #get silo choices for the dropdown
    silos = Silo.objects.filter(owner=request.user)
    silo_choices = [(0, ""), (-1, "Create new silo")]
    for silo in silos:
        silo_choices.append((silo.pk, silo.name))

    user_id = request.user.id

    try:
        commcare_token = ThirdPartyTokens.objects.get(user_id=request.user, name='CommCare')
    except (ThirdPartyTokens.MultipleObjectsReturned, ThirdPartyTokens.DoesNotExist):
        return redirect('getCommCareAuth')


    if request.method == 'POST':
        form = CommCareProjectForm(request.POST, silo_choices=silo_choices, user_id=user_id)
        silo_id = int(request.POST.get("silo", None))
        if silo_id == 0:
            silo_id = None

        if form.is_valid():
            project = request.POST['project']
            commcare_token = ThirdPartyTokens.objects.get(user=request.user, name=provider)
            auth_header = {'Authorization': 'ApiKey %(u)s:%(a)s' % {'u' : commcare_token.username, 'a' : commcare_token.token}}

            try:
                report_name = request.POST['commcare_report_name']
                report_id = None
                report_map = getCommCareReportIDs(project, auth_header)
                for id in report_map:
                    if report_map[id] == report_name:
                        report_id = id
                        break
            except MultiValueDictKeyError:
                report_name = None

            user = request.user

            if request.POST['download_type'] == 'commcare_form':
                download_type = 'form'
            elif request.POST['download_type'] == 'commcare_report':
                download_type = 'report'
            else:
                download_type = 'case'

            #prep url for finding size of dataset
            base_url = 'https://www.commcarehq.org/a/%s/api/v0.5/%s/'
            url = base_url % (project, download_type)


            #get size of dataset

            if download_type == 'report':
                url = base_url % (project, 'configurablereportdata')
                url = url + report_id + '?format=JSON&limit=1'
                response = requests.get(url, headers=auth_header)
                response_data = json.loads(response.content)
                data_count = response_data['total_records']

            else:
                url = base_url % (project, 'case')
                url = url + report_id + '?format=JSON&limit=1'
                data_count = response_data.get('meta').get('total_count')
                print 'got a total count', data_count


            # need to redo the url if downloading a reports

            url = url.replace('&limit=1', '')
            print 'penultimate url', url

            if report_name:
                read_name = '%s report - %s' % (project, report_name)
            else:
                read_name = project + ' cases'
            read, read_created = Read.objects.get_or_create(read_name=read_name, owner=user,
            defaults={'read_url': url, 'type': ReadType.objects.get(read_type=provider), 'description': ""})
            if read_created:
                read.save()

            requested_silo_name = request.POST.get('new_silo_name', None)
            silo, silo_created = Silo.objects.get_or_create(id=silo_id, defaults={"name": requested_silo_name, "public": False, "owner": request.user})
            if silo_created or read_created:
                silo.reads.add(read)
            elif read not in silo.reads.all():
                silo.reads.add(read)
            print 'hey look commcare form', request.POST['commcare_report_name']
            #get the actual data
            ret = getCommCareCaseData(url, auth_header, True, data_count, silo, read, request.POST['commcare_report_name'])
            messages.add_message(request,ret[0],ret[1])
            #need to impliment if import faluire
            cols = ret[2]
            return HttpResponseRedirect(reverse_lazy("siloDetail", kwargs={'silo_id' : silo.id}))

        else:
            messages.error(request, "Could not get data")
        return render(request, 'getcommcareforms.html', {'form': form})

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

        return render(request, 'getcommcareforms.html', {'form': form})


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
    auth_header = {'Authorization': 'ApiKey %(u)s:%(a)s' % {'u' : commcare_token.username, 'a' : commcare_token.token}}
    reports = getCommCareReportIDs(project, auth_header)
    return HttpResponse(json.dumps(reports))
