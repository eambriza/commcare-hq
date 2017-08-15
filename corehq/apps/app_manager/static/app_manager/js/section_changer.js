/**
 *  For pages with multiple section/panels, controls a dropdown menu that lets user
 *  select which sections to display. Expects a section changer menu somewhere on
 *  the page, which looks like this:

    <div class="section-changer btn-group" data-collapse-key="UNIQUE-SLUG-FOR-PAGE">
        <a class="btn btn-default dropdown-toggle" data-toggle="dropdown" href="#">
            <i class="fa fa-reorder"></i>
            <span class="caret"></span>
        </a>
        <ul class="dropdown-menu dropdown-menu-right checklist">
            <li class="dropdown-header">Show</li>
            <li>
                <a href="#" data-slug="SECTION-SLUG" data-collapse="1">
                    <i class="fa fa-check"></i>SECTION-NAME
                </a>
            </li>
            ... ADDITIONAL ITEMS ...
        </ul>
    </div>

 *  The corresponding panels need to be marked with matching slugs, like this:

    <div class="panel panel-appmanager" data-slug="SECTION-SLUG">
        <div class="panel-heading">
            <h4 class="panel-title panel-title-nolink">SECTION-NAME</h4>
        </div>
        <div class="panel-body">
            ... CONTENT ...
        </div>
    </div>

 *  When the user shows or hides a section, that preference is stored in localStorage.
 */
hqDefine("app_manager/js/section_changer", function() {
    // Determine key for localStorage
    // page is something like "module-view"
    // section is something like "logic"
    var getKey = function(page, section) {
        return _.template("app-manager-collapse-<%= page %>-<%= section %>")({
            page: page,
            section: section,
        });
    };

    // Determine if section should be shown or not, based on localStorage and given default
    var shouldCollapse = function(page, section, defaultCollapse) {
        var key = getKey(page, section);
        return localStorage.hasOwnProperty(key) ? localStorage.getItem(key) : defaultCollapse;
    };

    // Attach section changer UI to a form's save bar
    // $el can be the form or any element inside of it
    var attachToForm = function($el) {
        var $form = $el.closest("form");
        $el.find(".savebtn-bar").append($form.find(".section-changer").detach());
    };

    // Determine which items in the dropdown to select and (maybe) which panels to show.
    // This is a little squirrely because app settings works differently than module/form settings.
    // In module/form settings, by the time this module loads, all of the HTML is present on
    // the page, and when this runs, and the information about which panels to show (in the
    // absence of a preference in localStorage) is in data attributes in the changer itself.
    // In app settings, the whole page is generated by knockout, which hasn't run at this point,
    // and knockout also controls which sections are shown. So for that case, don't do anything
    // until the user clicks on the section changer, and then look at which panels are visible
    // to decide which changer items to mark selected.
    var init = function($sectionChanger) {
        var $form = $sectionChanger.closest("form");
        if ($sectionChanger.length) {
            $sectionChanger.find("ul a").each(function() {
                var $link = $(this),
                    slug = $link.data("slug"),
                    key = getKey($sectionChanger.data("collapse-key"), slug);
                if (!slug) {
                    return;
                }
                $link.data("collapse-key", key);
                if (shouldCollapse($sectionChanger.data("collapse-key"), slug, $link.data("collapse"))) {
                    $form.find(".panel-appmanager[data-slug='" + slug + "']").addClass("hide");
                } else {
                    $link.addClass("selected");
                }
            });
        }
    };
    $(function() {
        $(".section-changer").each(function() {
            var $changer = $(this);
            init($changer);
            $changer.children("a").one("click", function() {
                init($changer);
            });
        });
    });

    // Click handler for item in section changer
    $(document).on("click", ".section-changer ul a", function(e) {
        var $link = $(this),
            $panel = $link.closest("form").find(".panel-appmanager[data-slug='" + $link.data("slug") + "']");
        if ($link.hasClass("selected")) {
            $panel.addClass("hide");
        } else {
            $panel.removeClass("hide");
        }
        localStorage.setItem($link.data("collapse-key"), $link.hasClass("selected") ? "1" : "");
        $link.toggleClass("selected");
        e.preventDefault();
    });

    return {
        attachToForm: attachToForm,
        shouldCollapse: shouldCollapse,
    };
});
