from . import views
from django.conf.urls import url


urlpatterns = [
    # url(r'^$', views.getCommCareAuth, name='getCommCareAuth'),
    # url(r'^passform/', views.getCommCareFormPass, name='getCommCarePass'),
    url(r'^auth/$', views.getCommCareAuth, name='getCommCareAuth'),
    url(r'^$', views.getCommCareData, name='getCommCareData'),
    url(r'^logout/$', views.commcareLogout, name='commcareLogout'),
    url(r'^report_names/$', views.get_commcare_report_names,
        name='getCommCareReportNames'),
    url(r'^form_names/$', views.get_commcare_form_names,
        name='getCommCareFormNames')
]
