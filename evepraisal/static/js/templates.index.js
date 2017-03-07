$(function () {
    $("#result_form").submit(function () {
        var result = $("#raw_paste");
        var result_submit = $("#result_submit");
        // Disable form components
        result.attr("disabled", "disabled").addClass("disabled");
        result_submit.attr("disabled", "disabled").addClass("disabled");
        var url = $("#result_form").attr("action");

        $.post(url,
            {
            raw_paste: result.val(),
            hide_buttons: $("#hide-buttons").is(':checked'),
            paste_autosubmit: $("#paste-autosubmit").is(':checked'),
            market: $("#market").val(),
            save: $("#save").val() == "True"
        }, function (data) {
            result.val('');
            // Enable form components
            result.removeAttr("disabled").removeClass("disabled");
            result_submit.removeAttr("disabled").removeClass("disabled");
            //
            // Populate results
            //
            // The sensible person would use jQuery as it was below, but, it doesn't work...
            // So, instead back to document.
            //
            //$('#result_container').innerHTML = data;
            $('#result_container').html(data); // testing this<----
            //
            //document.getElementById('result_container').innerHTML = data;
            if (typeof(_gaq) != "undefined") {
                _gaq.push(['_trackEvent', 'estimate_cost', 'success']);
            }
        }).error(function () {
            // Enable form components
            result.removeAttr("disabled").removeClass("disabled");
            result_submit.removeAttr("disabled").removeClass("disabled");
            alert("Server responded with an error.");
            if (typeof(_gaq) != "undefined") {
                _gaq.push(['_trackEvent', 'estimate_cost', 'fail']);
            }
        });
        return false;
    });
    if ($("#autosubmit").val() == "True") {
        $("#raw_paste").bind('paste', function (e) {
            setTimeout(function () {
                $('#result_form').submit();
            }, 0);
        });
    }
});