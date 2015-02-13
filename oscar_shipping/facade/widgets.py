from django.core.urlresolvers import reverse_lazy

from oscar.forms.widgets import RemoteSelect, MultipleRemoteSelect

class PecomCitySelect(RemoteSelect):
    """
    PEC city code selector based on Select2 widget.
    
    """
    lookup_url = reverse_lazy('shipping:city-lookup', kwargs={'slug' : 'pek'})