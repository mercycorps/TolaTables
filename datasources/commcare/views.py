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
from .util import getCommCareCaseData

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
                return redirect('getCommCareData')
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
            try:
                report_name = request.POST['commcare_report_name']
            except MultiValueDictKeyError:
                report_name = None

            user = request.user

            if request.POST['download_type'] == 'commcare_form':
                download_type = 'form'
            elif request.POST['download_type'] == 'commcare_report':
                download_type = 'simplereportconfiguration'
            else:
                download_type = 'case'

            #prep url for finding size of dataset
            base_url = 'https://www.commcarehq.org/a/%s/api/v0.5/%s/'
            url = base_url % (project, download_type)
            if download_type == 'simplereportconfiguration':
                url + '?format=JSON'
            else:
                url + '?format=JSON&limit=1'
            print 'prepped url', url

            #get size of dataset
            commcare_token = ThirdPartyTokens.objects.get(user=request.user, name=provider)
            auth_header = {'Authorization': 'ApiKey %(u)s:%(a)s' % {'u' : commcare_token.username, 'a' : commcare_token.token}}
            response = requests.get(url, headers=auth_header)
            response_data = json.loads(response.content)
            if download_type == 'simplereportconfiguration':
                report_id = ''
                for rpt_info in response_data['objects']:
                    print 'this is hte report info', rpt_info
                    print 'title vs name', rpt_info['title'], report_name
                    if report_name == rpt_info['title']:
                        report_id = rpt_info['id']
                        break

                url = base_url % (project, 'configurablereportdata')
                url = url + report_id + '?limit=1&format=JSON'
                print 'this is the ultra new url', url
                response = requests.get(url, headers=auth_header)
                response_data = json.loads(response.content)
                print 'my response data is this', response_data
                total_cases = response_data['total_records']
                print 'report total cases', total_cases
            else:
                total_cases = response_data.get('meta').get('total_count')
                print 'got a total count', total_cases

            # need to redo the url if downloading a reports

            url.replace('&limit=1', '')
            print 'new url', url

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
            print 'he look commcare form', request.POST['commcare_report_name']
            #get the actual data
            ret = getCommCareCaseData(url, auth_header, True, total_cases, silo, read, request.POST['commcare_report_name'])
            messages.add_message(request,ret[0],ret[1])
            #need to impliment if import faluire
            cols = ret[2]
            return HttpResponseRedirect(reverse_lazy("siloDetail", kwargs={'silo_id' : silo.id}))

        else:
            messages.error(request, "Could not get data")
        return render(request, 'getcommcareforms.html', {'form': form})

    else:
        print 'ok maybe here'
        user_id = request.user.id


        form = CommCareProjectForm(user_id=user_id, silo_choices=silo_choices)
        return render(request, 'getcommcareforms.html', {'form': form})



    # cols = []
    # form = None
    # provider = "CommCare"
    # auth = 1
    # project = None
    # silos = Silo.objects.filter(owner=request.user)
    # silo_choices = [(0, ""), (-1, "Create new silo")]
    # user_id = request.user.id
    # total_cases = 0
    # for silo in silos:
    #     silo_choices.append((silo.pk, silo.name))
    #
    # if request.method == 'POST':
    #     #their exists a project and authorization so get the data
    #     form = CommCareProjectForm(request.POST, choices=silo_choices, user_id=user_id)
    #     commcare_form = request.POST['commcare_form_name']
    #
    #     if form.is_valid():
    #         try:
    #             created = False
    #             #either add a new commcare_auth token or retrieve an old one
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
    #                 # try:
    #                 read, read_created = Read.objects.get_or_create(read_name="%s cases" % project, owner=request.user,
    #                     defaults={'read_url': url, 'type': ReadType.objects.get(read_type=provider), 'description': ""})
    #                 if read_created: read.save()
    #                 # except Exception as e:
    #                 #     return HttpResponse("Invalid name and/or URL")
    #
    #                 new_silo_name = request.POST.get('new_silo_name', None)
    #                 silo, silo_created = Silo.objects.get_or_create(id=silo_id, defaults={"name": new_silo_name, "public": False, "owner": request.user})
    #                 if silo_created or read_created:
    #                     silo.reads.add(read)
    #                 elif read not in silo.reads.all():
    #                     silo.reads.add(read)
    #
    #                 #get the actual data
    #                 authorization = {'Authorization': 'ApiKey %(u)s:%(a)s' % {'u' : commcare_token.username, 'a' : commcare_token.token}}
    #                 ret = getCommCareCaseData(url, authorization, True, total_cases, silo, read, commcare_form)
    #                 messages.add_message(request,ret[0],ret[1])
    #                 #need to impliment if import faluire
    #                 cols = ret[2]
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
    #
    # return render(request, 'getcommcareforms.html', {'form': form, 'auth': auth, 'entries': total_cases, 'time' : timezone.now()})



# @login_required
# def getCommCareAuth(request):
#     """
#     Get the forms owned or shared with the logged in user
#     :param request:
#     :return: list of Ona forms paired with action buttons
#     """
#     cols = []
#     form = None
#     provider = "CommCare"
#     #If I can get the authorization token to work
#     auth = 1
#     commcare_token = None
#     url = "" #url to get the data contained
#     url1 = "https://www.commcarehq.org/a/"
#     url2 = "/api/v0.5/case/?format=JSON&limit=1"
#     project = None
#     silos = Silo.objects.filter(owner=request.user)
#     choices = [(0, ""), (-1, "Create new silo")]
#     user_id = request.user.id
#     total_cases = 0
#     for silo in silos:
#         choices.append((silo.pk, silo.name))
#
#     if request.method == 'POST':
#         #their exists a project and authorization so get the data
#         form = CommCareProjectForm(request.POST, choices=choices, user_id=user_id)
#
#         if form.is_valid():
#             try:
#                 created = False
#                 #either add a new commcare_auth token or retrieve an old one
#                 try:
#                     if request.POST['auth_token'] != '':
#                         commcare_token, created = ThirdPartyTokens.objects.get_or_create(user=request.user,name=provider,token=request.POST['auth_token'],username=request.POST['username'])
#                         form = CommCareAuthForm(request.POST, choices=choices, user_id=user_id)
#                         if form.is_valid():
#                             pass
#                 except Exception as e:
#                     commcare_token = ThirdPartyTokens.objects.get(user=request.user,name=provider)
#
#                 project = request.POST['project']
#                 url = url1 + project + url2
#                 response = requests.get(url, headers={'Authorization': 'ApiKey %(u)s:%(a)s' % {'u' : commcare_token.username, 'a' : commcare_token.token}})
#                 if response.status_code == 401:
#                     messages.error(request, "Invalid username, authorization token or project.")
#                     try:
#                         token = ThirdPartyTokens.objects.get(user=request.user, name="CommCare")
#                         token.delete()
#                     except Exception as e:
#                         pass
#                     form = CommCareAuthForm(choices=choices, user_id=user_id)
#                 elif response.status_code == 200:
#                     response_data = json.loads(response.content)
#                     total_cases = response_data.get('meta').get('total_count')
#                     if created: commcare_token.save()
#                     #add the silo and reads if necessary
#                     try:
#                         silo_id = int(request.POST.get("silo", None))
#                         if silo_id == 0:
#                             silo_id = None
#                     except Exception as e:
#                         return HttpResponse("Silo ID can only be an integer")
#
#                     # try:
#                     read, read_created = Read.objects.get_or_create(read_name="%s cases" % project, owner=request.user,
#                         defaults={'read_url': url, 'type': ReadType.objects.get(read_type=provider), 'description': ""})
#                     if read_created: read.save()
#                     # except Exception as e:
#                     #     return HttpResponse("Invalid name and/or URL")
#
#                     new_silo_name = request.POST.get('new_silo_name', None)
#                     silo, silo_created = Silo.objects.get_or_create(id=silo_id, defaults={"name": new_silo_name, "public": False, "owner": request.user})
#                     if silo_created or read_created:
#                         silo.reads.add(read)
#                     elif read not in silo.reads.all():
#                         silo.reads.add(read)
#
#                     #get the actual data
#                     authorization = {'Authorization': 'ApiKey %(u)s:%(a)s' % {'u' : commcare_token.username, 'a' : commcare_token.token}}
#                     ret = getCommCareCaseData(project, authorization, True, total_cases, silo, read)
#                     messages.add_message(request,ret[0],ret[1])
#                     #need to impliment if import faluire
#                     cols = ret[2]
#                     return HttpResponseRedirect(reverse_lazy("siloDetail", kwargs={'silo_id' : silo.id}))
#
#                 else:
#                     messages.error(request, "A %s error has occured: %s " % (response.status_code, response.text))
#                     form = CommCareAuthForm(choices=choices, user_id=user_id)
#             except KeyboardInterrupt as e:
#                 form = CommCareAuthForm(request.POST, choices=choices, user_id=user_id)
#                 form.is_valid()
#         else:
#             try:
#                 #look for authorization token
#                 commcare_token = ThirdPartyTokens.objects.get(user=request.user,name=provider)
#             except Exception as e:
#                 form = CommCareAuthForm(request.POST, choices=choices, user_id=user_id)
#
#     else:
#         try:
#             #look for authorization token
#             commcare_token = ThirdPartyTokens.objects.get(user=request.user,name=provider)
#             form = CommCareProjectForm(choices=choices, user_id=user_id)
#             auth = 0
#         except Exception as e:
#             form = CommCareAuthForm(choices=choices, user_id=user_id)
#
#     return render(request, 'getcommcareforms.html', {'form': form, 'data': cols, 'auth': auth, 'entries': total_cases, 'time' : timezone.now()})

# @login_required
# def getCommCareFormPass(request):
#     cols = []
#     form = None
#     provider = "CommCare"
#
#     #this version works without the token
#     url = "" #url to get the data contained
#     url1 = "https://www.commcarehq.org/a/"
#     url2 = "/api/v0.5/case/?format=JSON&limit=1"
#     project = None
#     silos = Silo.objects.filter(owner=request.user)
#     choices = [(0, ""), (-1, "Create new silo")]
#     user_id = request.user.id
#     total_cases = 0
#     for silo in silos:
#         choices.append((silo.pk, silo.name))
#
#     if request.method == 'POST':
#         form = CommCarePassForm(request.POST, choices=choices, user_id=user_id) #add the username and password to the request
#         if form.is_valid(): #does the form meet requierements
#             project = request.POST['project']
#             url = url1 + project + url2
#             response = requests.get(url, auth=HTTPDigestAuth(request.POST['username'], request.POST['password'])) #request the user data with a password and username
#             if response.status_code == 401:
#                 messages.error(request, "Invalid username, password or project.")
#             elif response.status_code == 200:
#                 response_data = json.loads(response.content)
#                 total_cases = response_data.get('meta').get('total_count')
#                 #add the silo and reads if necessary
#                 try:
#                     silo_id = int(request.POST.get("silo", None))
#                     if silo_id == 0: silo_id = None
#                 except Exception as e:
#                     return HttpResponse("Silo ID can only be an integer")
#
#                 # try:
#                 read, read_created = Read.objects.get_or_create(read_name="%s cases" % project, owner=request.user,
#                     defaults={'read_url': url, 'type': ReadType.objects.get(read_type=provider), 'description': ""})
#                 if read_created: read.save()
#                 # except Exception as e:
#                 #     return HttpResponse("Invalid name and/or URL")
#
#                 silo_name = request.POST.get('new_silo_name', "%s cases" % (project))
#                 silo, silo_created = Silo.objects.get_or_create(id=silo_id, defaults={"name": silo_name, "public": False, "owner": request.user})
#                 if silo_created or read_created:
#                     silo.reads.add(read)
#                 elif read not in silo.reads.all():
#                     silo.reads.add(read)
#
#                 #get the actual data
#                 auth = {"u" : request.POST['username'], "p" : request.POST['password']}
#                 ret = getCommCareCaseData(project, auth, False, total_cases, silo, read)
#                 #need to impliment if import faluire
#                 messages.add_message(request,ret[0],ret[1])
#                 cols = ret[2]
#                 return HttpResponseRedirect(reverse_lazy("siloDetail", kwargs={'silo_id' : silo.id}))
#
#             else:
#                 messages.error(request, "A %s error has occured: %s " % (response.status_code, response.text))
#     else:
#         form = CommCarePassForm(choices=choices, user_id=user_id)
#
#
#     return render(request, 'getcommcareforms.html', {'form': form, 'data': cols, 'auth': 2, 'entries': total_cases})


@login_required
def commcareLogout(request):
    try:
        token = ThirdPartyTokens.objects.get(user=request.user, name="CommCare")
        token.delete()
    except Exception as e:
        pass

    messages.error(request, "You have been logged out of your CommCare account.  Any Tables you have created with this account ARE still available, but you must log back in here to update them.")
    return HttpResponseRedirect(reverse_lazy('getCommCareAuth'))
