from decimal import Decimal as D

from oscar.core import prices
from oscar.apps.checkout.session import CheckoutSessionMixin as CoreCheckoutSessionMixin
from oscar.core.loading import get_class

#CoreCheckoutSessionMixin = get_class('checkout.session', 'CheckoutSessionMixin')
Repository = get_class('shipping.repository', 'Repository')

class CheckoutSessionMixin(CoreCheckoutSessionMixin):

    def use_shipping_kwargs(self, kwargs):
        self.checkout_session._set('shipping', 'options', kwargs)

    def get_available_shipping_methods(self):
        """
        Returns all applicable shipping method objects for a given basket.
        """
        # Shipping methods can depend on the user, the contents of the basket
        # and the shipping address (so we pass all these things to the
        # repository).  I haven't come across a scenario that doesn't fit this
        # system.
        return Repository().get_shipping_methods(
            basket=self.request.basket, user=self.request.user,
            shipping_addr=self.get_shipping_address(self.request.basket),
            request=self.request)

    def get_shipping_kwargs(self):
        return self.checkout_session._get('shipping', 'options')
    
    def get_shipping_charge(self, basket):
        shipping_charge = prices.Price(
            currency=basket.currency, excl_tax=D('0.00'), incl_tax=D('0.00'))
        shipping_address = self.get_shipping_address(basket)
        shipping_method = self.get_shipping_method(
            basket, shipping_address)
        if shipping_method:
            shipping_kwargs = self.get_shipping_kwargs()
            shipping_charge = shipping_method.calculate(basket, shipping_kwargs or None)
        else:
            # It's unusual to get here as a shipping method should be set by
            # the time this skip-condition is called. In the absence of any
            # other evidence, we assume the shipping charge is zero.
            #shipping_charge = D('0.00')
            pass
        return shipping_charge

    def skip_unless_payment_is_required(self, request):
        # Check to see if payment is actually required for this order.
        
        shipping_charge = self.get_shipping_charge(request.basket)
        total = self.get_order_totals(request.basket, shipping_charge)
        
        if total.excl_tax == D('0.00'):
            raise exceptions.PassedSkipCondition(
                url=reverse('checkout:preview')
            )

    def build_submission(self, **kwargs):
        """
        Return a dict of data that contains everything required for an order
        submission.  This includes payment details (if any).

        This can be the right place to perform tax lookups and apply them to
        the basket.
        """
        shipping_kwargs = {}
        basket = kwargs.get('basket', self.request.basket)
        shipping_address = self.get_shipping_address(basket)
        shipping_method = self.get_shipping_method(
            basket, shipping_address)
        billing_address = self.get_billing_address(shipping_address)
        if not shipping_method:
            total = shipping_charge = None
        else:
            shipping_kwargs = self.get_shipping_kwargs()
#             if shipping_kwargs:
#                 shipping_charge = shipping_method.calculate(basket, shipping_kwargs)
#             else:
#                 shipping_charge = shipping_method.calculate(basket)
            shipping_charge = shipping_method.calculate(basket, shipping_kwargs or None)
            total = self.get_order_totals(
                basket, shipping_charge=shipping_charge)
        submission = {
            'user': self.request.user,
            'basket': basket,
            'shipping_address': shipping_address,
            'shipping_method': shipping_method,
            'shipping_charge': shipping_charge,
            'billing_address': billing_address,
            'order_total': total,
            # Details for shipping charge
            #'shipping_kwargs' : shipping_kwargs,
            'order_kwargs': {},
            'payment_kwargs': {}}
        
        # If there is a billing address, add it to the payment kwargs as calls
        # to payment gateways generally require the billing address. Note, that
        # it normally makes sense to pass the form instance that captures the
        # billing address information. That way, if payment fails, you can
        # render bound forms in the template to make re-submission easier.
        if billing_address:
            submission['payment_kwargs']['billing_address'] = billing_address

        # Allow overrides to be passed in
        submission.update(kwargs)

        # Set guest email after overrides as we need to update the order_kwargs
        # entry.
        if (not submission['user'].is_authenticated() and
                'guest_email' not in submission['order_kwargs']):
            email = self.checkout_session.get_guest_email()
            submission['order_kwargs']['guest_email'] = email
        
        return submission
    
    