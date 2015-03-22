from django import forms
from django.forms.widgets import RadioSelect
from django.utils.html import format_html_join
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse_lazy

from .widgets import PecomCitySelect, PecomCityDetails

class BasePecomForm(forms.Form):
    senderCityId = forms.IntegerField(widget=forms.HiddenInput)
    receiverCityId = forms.IntegerField(widget=forms.HiddenInput)
    transportingType = forms.IntegerField(widget=forms.HiddenInput, required=False)

class PecomCalcForm(BasePecomForm):

    def __init__(self, *args, **kwargs):
        lookup_url = None
        choices = None
        options = None
        full_form = False
        details_url = reverse_lazy('shipping:charge-details', kwargs={'slug':'pek'})
        
        if 'details_url' in kwargs.keys():
            details_url = kwargs.pop('details_url')
        if 'lookup_url' in kwargs.keys():
            lookup_url = kwargs.pop('lookup_url')
        if 'choices' in kwargs.keys():
            choices = kwargs.pop('choices')
        if 'options' in kwargs.keys():
            options = kwargs.pop('options')
        if 'full' in kwargs.keys():
            full_form = kwargs.pop('full')
        
              
        super(PecomCalcForm, self).__init__(*args, **kwargs)
        if lookup_url:
            # single city selector
            self.fields['receiverCityId'] = forms.ChoiceField(label=_("Destination city"), 
                                              widget=PecomCitySelect(lookup_url=lookup_url,
                                                             css='single-city-selector',
                                                             attrs={'data-lookup-url' : details_url,
                                                                }))
        if choices:
            # choose between found cities
            self.fields.pop('transportingType')
            self.fields['receiverCityId'] = forms.ChoiceField(label=_("Destination city"),
                                                              choices=choices, 
                                                              widget=PecomCityDetails(attrs={'class' : 'city-selector',
                                                                                        'data-lookup-url' : details_url,
                                                                                        }))
        if options:
            # choose shipping details
            if not full_form:
                self.fields.pop('senderCityId')
                self.fields.pop('receiverCityId')
            options = [ (o['id'], _(u"%s: %s RUR. Including: <ul>%s</ul>") % (o['name'],
                                                  o['cost'],
                                                  format_html_join('\n', 
                                                     u"<li>{3} {2} ({0}, {1})</li>", 
                                                     (( s['serviceType'], 
                                                        s['senderCity'], 
                                                        s['cost'],
                                                        s['info']
                                                        ) for s in o['services']))
                                                  ) 
                         ) for o in options  ] 
            
            self.fields['transportingType'] = forms.ChoiceField(label=_("Type of transportation"),
                                                                help_text = _("Please choose the transportation type"),
                                                                choices=options, 
                                                                widget=RadioSelect,
                                                                required=True)

class EmsCalcForm(forms.Form):
    senderCityId = forms.CharField(widget=forms.HiddenInput)
    receiverCityId = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        lookup_url = None
        choices = None
        options = None
        details_url = reverse_lazy('shipping:charge-details', kwargs={'slug':'ems'})

        if 'details_url' in kwargs.keys():
            details_url = kwargs.pop('details_url')
        if 'lookup_url' in kwargs.keys():
            lookup_url = kwargs.pop('lookup_url')  
        if 'choices' in kwargs.keys():
            choices = kwargs.pop('choices')            
        if 'options' in kwargs.keys():
            options = kwargs.pop('options')

        super(EmsCalcForm, self).__init__(*args, **kwargs)

        if lookup_url:
            # single city selector
            self.fields['receiverCityId'] = forms.ChoiceField(label=_("Destination city"), 
                                              widget=PecomCitySelect(lookup_url=lookup_url,
                                                             css='single-city-selector',
                                                             attrs={'data-lookup-url' : details_url,
                                                                }))
        if choices:
            # choose between found cities
            self.fields['receiverCityId'] = forms.ChoiceField(label=_("Destination city"),
                                                              choices=choices, 
                                                              widget=PecomCityDetails(attrs={'class' : 'city-selector',
                                                                                        'data-lookup-url' : details_url,
                                                                                        }))
            
        