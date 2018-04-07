import json
import requests

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse, reverse_lazy
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import redirect, render

from silo.models import Silo, Read, ReadType, ThirdPartyTokens
from commcare.models import CommCareCache
from commcare.forms import CommCareAuthForm, CommCareProjectForm
from commcare.util import getCommCareDataHelper, get_commcare_record_count, \
    CommCareImportConfig, get_commcare_report_ids


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
            ping_url = 'https://www.commcarehq.org/a/%s/api' \
                '/v0.5/case/?limit=1' \
                % request.POST['project']
            headers = {'Authorization': 'ApiKey %(u)s:%(a)s' % {
                    'u': request.POST['username'],
                    'a': request.POST['auth_token']
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
                    name=provider,
                    user_id=request.user.id,
                    token=request.POST['auth_token'],
                    username=request.POST['username'])
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
            # Look for authorization token
            commcare_token = ThirdPartyTokens.objects.get(
                user=request.user, name=provider
            )
            return redirect('getCommCareData')

        # Catch an issue where there is more than one token in the DB.
        # This should never happen, but just in case.
        except ThirdPartyTokens.MultipleObjectsReturned:
            messages.error(
                request,
                "There was a problem with your login.  \
                    Please re-enter your login information.")
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
    conf = CommCareImportConfig()

    conf.tables_user_id = request.user.id

    # If the token can't be retrieved, redirect them to the auth page.
    try:
        conf.set_auth_header()
        conf.use_token = True
    except (ThirdPartyTokens.MultipleObjectsReturned,
            ThirdPartyTokens.DoesNotExist):
        return redirect('getCommCareAuth')

    # Get silo choices for dropdown
    silos = Silo.objects.filter(owner=request.user)
    silo_choices = [(0, ""), (-1, "Create a new Table")]
    for silo in silos:
        silo_choices.append((silo.pk, silo.name))

    if request.method == 'POST':

        # Update the config object with form selections
        conf.silo_id = int(request.POST.get("silo", None))
        if conf.silo_id in [-1, 0]:
            conf.silo_id = None

        conf.project = request.POST['project']

        report_choices = [('default', 'Select a Report')]
        try:
            conf.report_id = request.POST['commcare_report_name']
            report_map = get_commcare_report_ids(conf)
            report_choices.extend([(k, v) for k, v in report_map.iteritems()])
        except KeyError:
            conf.report_id = False

        commcare_form_choices = [('default', 'Select a Form')]
        try:
            conf.form_id = request.POST['commcare_form_name']
            db_forms = CommCareCache.objects.filter(conf.project) \
                .values('form_id', 'form_name')
            commcare_form_choices.extend(db_forms)
        except KeyError:
            conf.form_id = False

        form = CommCareProjectForm(
            request.POST,
            silo_choices=silo_choices,
            report_choices=report_choices,
            user_id=conf.tables_user_id
        )

        if form.is_valid():

            if conf.report_id != 'default':
                report_name = report_map[conf.report_id]
            else:
                report_name = None

            conf.download_type = request.POST['download_type']
            base_url = 'https://www.commcarehq.org/a/%s/api/v0.5/%s/'

            # Set url and get size of dataset.  KeyError will be thrown by
            # get_commcare_record_count when CommCare API isn't working
            try:
                if conf.download_type == 'commcare_report':
                    conf.base_url = base_url % (
                        conf.project, 'configurablereportdata')
                    conf.base_url += conf.report_id + '/?format=JSON&limit=1'
                    conf.record_count = get_commcare_record_count(conf)
                elif conf.download_type == 'commcare_form':
                    conf.base_url = base_url % (
                        conf.project, 'form') + '?limit=1'
                    conf.record_count = get_commcare_record_count(conf)
                else:
                    conf.base_url = base_url % (conf.project, 'case') + \
                        '?format=JSON&limit=1'
                    conf.record_count = get_commcare_record_count(conf)
            except KeyError:
                messages.add_message(
                    request,
                    messages.ERROR,
                    "The CommCare API is not responding.  \
                        Please try again later")
                return render(
                    request,
                    'getcommcareforms.html',
                    {'form': form, 'auth': 'authenticated'})

            if conf.download_type == 'commcare_report':
                read_name = '%s report - %s' % (conf.project, report_name)
            elif conf.download_type == 'commcare_form':
                read_name = '%s form - %s' % (conf.project, report_name)
            else:
                read_name = conf.project + ' cases'
            read = Read.objects.create(
                read_name=read_name,
                owner=request.user,
                read_url=conf.base_url,
                type=ReadType.objects.get(read_type=provider),
                description="")
            conf.read_id = read.id

            requested_silo_name = request.POST.get('new_table_name', None)
            silo, silo_created = Silo.objects.get_or_create(
                id=conf.silo_id,
                defaults={"name": requested_silo_name, "public": False,
                          "owner": request.user})
            if silo_created:
                silo.reads.add(read)
            elif read not in silo.reads.all():
                silo.reads.add(read)
            conf.silo_id = silo.id

            # Retrieve and save the data.
            # TODO: catch retrieval failures
            ret = getCommCareDataHelper(conf)
            messages.add_message(request, ret[0], ret[1])

            return HttpResponseRedirect(reverse_lazy(
                "siloDetail", kwargs={'silo_id': silo.id}))

        # Need to implement some sort of error catching code here.  CommCare
        # sometimes returns html error messages to API calls
        # else:
        #     for m in messages.get_messages(request):
        #         print 'm e ss', m
        #     messages.error(request, "Could not get data")
        return render(
            request,
            'getcommcareforms.html',
            {'form': form, 'auth': 'authenticated'})

    else:
        user_id = request.user.id
        form = CommCareProjectForm(
            user_id=user_id,
            silo_choices=silo_choices,
        )
        try:
            form.fields['project'].initial = request.GET.get('project')
        except Exception:
            pass

        return render(
            request,
            'getcommcareforms.html',
            {'form': form, 'auth': 'authenticated'})


@login_required
def commcareLogout(request):
    try:
        token = ThirdPartyTokens.objects.get(
            user=request.user, name="CommCare")
        token.delete()
    except Exception:
        pass

    messages.error(request, "You have been logged out of your CommCare \
        account.  Any Tables you have created with this account ARE still \
        available, but you must log back in here to update them.")
    return HttpResponseRedirect(reverse_lazy('getCommCareAuth'))


@login_required
def get_commcare_report_names(request):
    conf = CommCareImportConfig(
        project=request.GET['project'], tables_user_id=request.user.id
    )
    conf.set_auth_header()
    reports = get_commcare_report_ids(conf)
    return HttpResponse(json.dumps(reports))


@login_required
def get_commcare_form_names(request):
    commcare_forms = CommCareCache.objects.filter(
        project=request.GET['project'])
    form_map = {}
    for cform in commcare_forms:
        form_map[cform.form_id] = cform.form_name
    return HttpResponse(json.dumps(form_map))
