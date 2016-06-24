$(document).ready(function() {
	function remove_form(obj){
		var details_div = obj.closest('form').find('.shipping-details-form');
		if (details_div) {
			details_div.fadeOut(10000);
			details_div.remove();	
		}
	}

	function get_method_code(obj){
		return $(obj).parents('form').find('input[name="method_code"]').val();
	}

	function trans_type_handler (event){
		var method_code = get_method_code(this),
			charge = $(this).next().find('.shipping-charge').html();
		$('#shipping-charge-'+method_code).html(charge);
		console.log(charge+' '+method_code);
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
						var method_code = get_method_code(this);
						if (method_code) {
							$('#shipping-charge-' + method_code).html('<div id="wait">calculating...</div>');

						} else {
							$(this).after('<div id="wait">calculating...</div>');
						}

				    },
        			complete: function() { 
        				$('#wait').remove();
        			}, 
				    data: {'from': $(this).closest('form').find("input[name='senderCityId']:hidden:first").val(), 
				            'to': $(this).val()}, 
				    context: this,
				    success: function(data, status) {
						var method_code = get_method_code(this);
						if (!method_code){
							method_code = data.method_code;
						}
						if (data.content_html) {
							$(this).nextAll('.lookup-result').html(data.content_html);
							$('#shipping-charge-'+method_code).html(data.charge);
							$('input[name="transportingType"]').change(trans_type_handler);
						} else {
							$(this).after('Sorry. No data received');
						}
						if (data.error) {
							console.log(data.error);
						}

				    }
			});
			event.handled = true;
		}
		return false;            		
    }
    // bind classes select2 single-city-selector' onchange event 
    $('.city-selector, .single-city-selector')
    .change(ajax_handler); 

	$('input[name="transportingType"]').change(trans_type_handler)
}); 

