$(document).ready(function() {
	function remove_form(obj){
		var details_div = obj.closest('form').find('.shipping-details-form');
		if (details_div) {
			details_div.fadeOut(10000);
			details_div.remove();	
		}
	}
	
	function ajax_handler(event){
		// event.handled intended to prevent firing handler multiple times
		// see http://sholsinger.com/2011/08/prevent-jquery-live-handlers-from-firing-multiple-times/
		if (event.handled !== true){
			remove_form($(this));
			$.ajax({ 
				    type: $(this).attr('method'), 
				    url: $(this).data('lookup-url'),
				    beforeSend: function() { 
				    	$(this).after('<div id="wait">calculating...</div>');
				    },
        			complete: function() { 
        				$('#wait').remove();
        			}, 
				    data: {'from': $(this).closest('form').find("input[name='senderCityId']:hidden:first").val(), 
				            'to': $(this).val()}, 
				    context: this,
				    success: function(data, status) {
				        $(this).after(data);
				    }
			});
			event.handled = true;
		}
		return false;            		
    }
    // bind classes select2 single-city-selector' onchange event 
    $('.city-selector, .single-city-selector')
    .change(ajax_handler); 
		
}); 

