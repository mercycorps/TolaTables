import json
from django.core.urlresolvers import reverse_lazy

from django.forms import ModelForm
from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Submit, Reset, HTML, Button, Row, Field, Hidden
from crispy_forms.bootstrap import FormActions
from django.forms.formsets import formset_factory
from django.utils.safestring import mark_safe

from .util import getProjects
from silo.models import ThirdPartyTokens


#diplaying a charfield that is also a list
class ListTextWidget(forms.TextInput):
    def __init__(self, data_list, name, *args, **kwargs):
        super(ListTextWidget, self).__init__(*args, **kwargs)
        self._name = name
        self._list = data_list
        self.attrs.update({'list':'list__%s' % self._name})

    def render(self, name, value, attrs=None):
        text_html = super(ListTextWidget, self).render(name, value, attrs=attrs)
        data_list = '<datalist id="list__%s">' % self._name
        for item in self._list:
            data_list += '<option value="%s">' % item
        data_list += '</datalist>'

        return (text_html + data_list)


class CommCareProjectForm(forms.Form):
    project = forms.CharField(required=True, help_text=mark_safe(
        """
        This is the name of the project you are importing from. Press the
        down arrow to see the name of past projects you have imported from.
        The projects your account has access to are listed in your CommCare
        <a href='https://www.commcarehq.org/account/projects/'
        target='_blank'>settings</a> under my projects.
        <br/><br/>
        If you are not getting access it could be because your project has
        a different name then what you as a user can see. To see
        your projects true name go to CommCare
        <a href='https://www.commcarehq.org/account/projects/'
        target='_blank'>settings</a>
        """
    ))
    silo = forms.ChoiceField(required=True)
    new_table_name = forms.CharField(required=False)

    # TYPE_CHOICES = [('commcare_report', 'Report'), ('commcare_form', 'Form'), ('cases', 'Cases')]
    TYPE_CHOICES = [('commcare_report', 'Report'), ('cases', 'Cases')]
    download_type = forms.ChoiceField(choices=TYPE_CHOICES, widget=forms.RadioSelect())
    commcare_report_name = forms.ChoiceField(required=False)
    commcare_form_name = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        from django.core.serializers.json import DjangoJSONEncoder
        silo_choices = kwargs.pop('silo_choices')
        user_id = kwargs.pop('user_id')
        report_choices = kwargs.pop('report_choices', '')
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-sm-3'
        self.helper.field_class = 'col-sm-8'
        self.helper.form_method = 'post'
        self.helper.form_id = 'commcare-import-form'
        self.helper.form_action = reverse_lazy('getCommCareData')
        self.helper.add_input(Submit('submit', 'Submit'))
        self.helper.add_input(Reset('rest', 'Reset', css_class='btn-warning'))
        super(CommCareProjectForm, self).__init__(*args, **kwargs)
        self.fields['project'].widget = ListTextWidget(data_list=getProjects(user_id), name='projects')
        self.fields['silo'].choices = silo_choices
        self.fields['silo'].label = 'Table'
        self.fields['new_table_name'].label = 'New table name*'
        self.fields['commcare_report_name'].choices = report_choices
        self.fields['commcare_report_name'].label = 'CommCare report name*'
        self.fields['commcare_form_name'].label = 'CommCare form name*'

    def clean(self):
        cleaned_data = super(CommCareProjectForm, self).clean()
        download_type = cleaned_data.get('download_type')
        commcare_report_name = cleaned_data.get('commcare_report_name')
        commcare_form_name = cleaned_data.get('commcare_form_name')
        new_table_name = cleaned_data.get('new_table_name')
        silo = cleaned_data.get('silo')
        has_errors = False
        if download_type == 'commcare_report' and commcare_report_name == 'default':
            self.add_error('commcare_report_name', "You must choose a report from the dropdown")
            has_errors = True
        if int(silo) == 0:
            self.add_error('silo', "You must select or create a Table.")
            has_errors = True
        if int(silo) == -1 and new_table_name == '':
            self.add_error('silo','')
            self.add_error('new_table_name', "You must provide a table name")
            has_errors = True
        
        if has_errors:
            raise forms.ValidationError("Your submission has errors")

        return cleaned_data



class CommCareAuthForm(forms.Form):
    username = forms.CharField(max_length=60, required=True)
    auth_token = forms.CharField(required=True, widget=forms.PasswordInput(), help_text=mark_safe("This gives tola access to your CommCare reports. Your api key can be found in your CommCare <a href='https://www.commcarehq.org/account/settings/' target='_blank'>settings</a>"))
    project = forms.CharField(max_length=60, required=True)

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Submit'))
        super(CommCareAuthForm, self).__init__(*args, **kwargs)
        self.fields['auth_token'].label = 'API Key'
