from django.core.urlresolvers import reverse_lazy
from django import forms

from oscar.forms.widgets import RemoteSelect

class PecomCitySelect(RemoteSelect):
    """
    PEC city code selector based on Select2 widget.
    
    """
    lookup_url = reverse_lazy('shipping:city-lookup', kwargs={'slug' : 'pek'})

    def __init__(self, *args, **kwargs):
        super(PecomCitySelect, self).__init__(*args, **kwargs)
        
    class Media:
        js = ('oscar_shipping/js/pecom_city_details.js', 
              )        

class PecomCityDetails(forms.RadioSelect):
    
    class Media:
        js = ('oscar_shipping/js/pecom_city_details.js', 
              )        