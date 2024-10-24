hqDefine('export/js/utils', [
    'jquery',
    'knockout',
    'underscore',
    'export/js/const',
], function (
    $,
    ko,
    _,
    constants
) {
    var getTagCSSClass = function (tag) {
        var cls = 'badge';
        if (tag === constants.TAG_DELETED) {
            return cls + ' text-bg-warning';
        } else {
            return cls + ' text-bg-secondary';
        }
    };

    var redirect = function (url) {
        window.location.href = url;
    };

    var animateToEl = function (toElementSelector, callback) {
        $('html, body').animate({
            scrollTop: $(toElementSelector).offset().top + 'px',
        }, 'slow', undefined, callback);
    };

    var capitalize = function (string) {
        return string.charAt(0).toUpperCase() + string.substring(1).toLowerCase();
    };

    return {
        getTagCSSClass: getTagCSSClass,
        redirect: redirect,
        animateToEl: animateToEl,
        capitalize: capitalize,
    };
});
