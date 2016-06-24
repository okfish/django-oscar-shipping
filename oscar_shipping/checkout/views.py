from django.contrib import messages
from django.utils.translation import ugettext_lazy as _
from django.shortcuts import redirect

from oscar.apps.checkout import views
from oscar.core.loading import get_class

from .session import CheckoutSessionMixin
#CheckoutSessionMixin = get_class('checkout.session', 'CheckoutSessionMixin')

class ShippingMethodView(views.ShippingMethodView):
    """
    View for a user to choose which shipping method(s) they want to use.
    """
    def get_context_data(self, **kwargs):
        kwargs = super(ShippingMethodView, self).get_context_data(**kwargs)
        kwargs['methods'] = self._methods
        return kwargs

    def form_valid(self, form):
        method_form = None
        request = self.request
        method_code = form.cleaned_data['method_code']
        self.checkout_session.use_shipping_method(method_code)
        method = self.get_shipping_method(request.basket, self.get_shipping_address(request.basket))
        
        try:
            method_form = method.facade.get_extra_form(request.POST or None)
        except AttributeError:
            pass
        if method_form:    
            if method_form.is_valid():
                messages.info(request, _("Shipping method %s selected") % method.name)
                self.use_shipping_kwargs(method_form.cleaned_data)
            else:
                messages.error(request, method_form.errors)
                return redirect('checkout:shipping-method')
        
        return self.get_success_response()
            
   
class PaymentMethodView(views.PaymentMethodView):
    pass

class PaymentDetailsView(views.PaymentDetailsView):
    pass