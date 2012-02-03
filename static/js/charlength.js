jQuery.fn.charLengthValidation = function(opts) {
    return this.keyup(function() {
        var charsLeft = opts.maxLength - $(this).val().length;
        if (charsLeft >= 0) {
            $(opts.validationSelector + ' .value').text(charsLeft);
            $(opts.validationSelector).toggleClass('invalid', charsLeft < opts.warning);
        } else {
            $(this).val($(this).val().substring(0, opts.maxLength));
        }
    }).trigger('keyup');
}