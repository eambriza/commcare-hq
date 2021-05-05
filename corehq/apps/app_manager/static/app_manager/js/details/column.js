/**
 * Model for a column in the Display Properties section of case list/detail.
 *
 * Initialize with a col and a screen:
 *  - col is the configuration of the column itself, basically a JSON version of
 *    the python DetailColumn model.
 *  - screen is a js model of the table that contains the column.
 *
 * On case detail screens, tabs are implemented as columns with a different
 * set of properties that match python's DetailTab model. The screen model
 * is responsible for creating the tab "columns" and injecting them into itself.
 */
hqDefine("app_manager/js/details/column", function () {
    var uiElement = hqImport('hqwebapp/js/ui-element');

    return function (col, screen) {
        /*
            column properties: model, field, header, format
            column extras: enum, late_flag
        */
        var self = {};
        hqImport("hqwebapp/js/main").eventize(self);
        self.original = JSON.parse(JSON.stringify(col));

        // Set defaults for normal (non-tab) column attributes
        var Utils = hqImport('app_manager/js/details/utils');
        var defaults = {
            calc_xpath: ".",
            enum: [],
            field: "",
            filter_xpath: "",
            format: "plain",
            graph_configuration: {},
            hasAutocomplete: false,
            header: {},
            model: screen.model,
            date_format: "",
            time_ago_interval: Utils.TIME_AGO.year,
        };
        _.each(_.keys(defaults), function (key) {
            self.original[key] = self.original[key] || defaults[key];
        });
        self.original.late_flag = _.isNumber(self.original.late_flag) ? self.original.late_flag : 30;

        self.original.case_tile_field = ko.utils.unwrapObservable(self.original.case_tile_field) || "";
        self.case_tile_field = ko.observable(self.original.case_tile_field);

        // Set up tab attributes
        var tabDefaults = {
            isTab: false,
            hasNodeset: false,
            nodesetType: "",
            nodesetIdentifier: screen.otherCaseTypes[0] || "",
            nodesetXpath: "",
            relevant: "",
        };
        _.each(_.keys(tabDefaults), function (key) {
            self.original[key] = self.original[key] || tabDefaults[key];
        });
        _.extend(self, _.pick(self.original, _.keys(tabDefaults)));

        self.screen = screen;
        self.lang = screen.lang;
        self.model = uiElement.select([{
            label: "Case",
            value: "case",
        }]).val(self.original.model);

        var icon = Utils.isAttachmentProperty(self.original.field) ? 'fa fa-paperclip' : null;
        self.field = undefined;
        if (self.original.hasAutocomplete) {
            self.field = uiElement.select();
        } else {
            self.field = uiElement.input(self.original.field);
        }
        self.field.setIcon(icon);

        // Make it possible to observe changes to self.field
        // note self observableVal is read only!
        // Writing to it will not update the value of the self.field text input
        self.field.observableVal = ko.observable(self.field.val());
        self.field.on("change", function () {
            self.field.observableVal(self.field.val());
        });

        (function () {
            var i,
                lang,
                visibleVal = "",
                invisibleVal = "";
            if (self.original.header && self.original.header[self.lang]) {
                visibleVal = invisibleVal = self.original.header[self.lang];
            } else {
                for (i = 0; i < self.screen.langs.length; i += 1) {
                    lang = self.screen.langs[i];
                    if (self.original.header[lang]) {
                        visibleVal = self.original.header[lang] +
                            hqImport('hqwebapp/js/ui_elements/ui-element-langcode-button').LANG_DELIN +
                            lang;
                        break;
                    }
                }
            }
            self.header = uiElement.input().val(invisibleVal);
            self.header.setVisibleValue(visibleVal);

            // TODO: extract into file
            var nodesetUiElement = function (options) {
                var self = {};

                self.nodesetXpath = ko.observable(options.nodesetXpath);

                self.dropdownOptions = _.map(options.caseTypes, function (t) {
                    return {name: gettext("Child cases: ") + t, value: t};
                }).concat([{name: gettext("Custom Nodeset"), value: ""}]);

                self.dropdownValue = ko.observable(_.find(self.dropdownOptions, function (o) {
                    return o.value === options.nodesetIdentifier;
                }));

                self.showXpath = ko.computed(function () {
                    return !self.dropdownValue().value;
                });

                var ui = '<select class="form-control" data-bind="options: dropdownOptions, optionsText: \'name\', value: dropdownValue"></select>';
                ui += '<textarea type="text" class="form-control" data-bind="value: nodesetXpath, visible: showXpath" style="margin-top: 5px" /></textarea>'
                if (hqImport('hqwebapp/js/toggles').toggleEnabled('SYNC_SEARCH_CASE_CLAIM')) {
                    ui += '<p data-bind="visible: showXpath() && nodesetXpath()" class="help-block">' + gettext("This data will not be shown for case search results.") + '</p>';
                }
                self.ui = $('<div>' + ui + '</div>');
                self.ui.koApplyBindings(self);

                hqImport("hqwebapp/js/main").eventize(self);
                self.nodesetXpath.subscribe(function () {
                    self.fire('change');
                });
                self.dropdownValue.subscribe(function () {
                    self.fire('change');
                });

                return self;
            };
            self.nodeset_extra = nodesetUiElement(_.extend({
                caseTypes: self.screen.otherCaseTypes,
            }, _.pick(self.original, ['nodesetType', 'nodesetIdentifier', 'nodesetXpath'])));   // TODO: remove nodesetType?

            self.relevant = uiElement.input().val(self.original.relevant);
            if (self.isTab) {
                self.header.ui.find("input[type='text']").attr("placeholder", gettext("Tab Name"));
                self.relevant.ui.find("input[type='text']").attr("placeholder", gettext("Display Condition"));

                if (self.original.relevant) {
                    self.relevant.observableVal = ko.observable(self.original.relevant);
                    self.relevant.on("change", function () {
                        self.relevant.observableVal(self.relevant.val());
                    });
                }
            }
        }());

        self.saveAttempted = ko.observable(false);
        self.useXpathExpression = self.original.useXpathExpression;
        self.showWarning = ko.computed(function () {
            if (self.useXpathExpression) {
                return false;
            }
            if (self.isTab) {
                // Data tab missing its nodeset
                return self.hasNodeset && !self.nodeset_extra.dropdownValue().value && !self.nodeset_extra.nodesetXpath();
            }
            // Invalid property name
            return (self.field.observableVal() || self.saveAttempted()) && !Utils.isValidPropertyName(self.field.observableVal());
        }, self);

        // Add the graphing option if self is a graph so self we can set the value to graph
        var menuOptions = Utils.getFieldFormats();
        if (self.original.format === "graph") {
            menuOptions = menuOptions.concat([{
                value: "graph",
                label: "",
            }]);
        }
        if (self.screen.columnKey === "long") {
            menuOptions = menuOptions.concat([{
                value: "markdown",
                label: gettext('Markdown'),
            }]);
        }

        if (self.useXpathExpression) {
            var menuOptionsToRemove = ['picture', 'audio'];
            for (var i = 0; i < menuOptionsToRemove.length; i++) {
                for (var j = 0; j < menuOptions.length; j++) {
                    if (
                        menuOptions[j].value !== self.original.format
                        && menuOptions[j].value === menuOptionsToRemove[i]
                    ) {
                        menuOptions.splice(j, 1);
                    }
                }
            }
        }

        self.format = uiElement.select(menuOptions).val(self.original.format || null);

        (function () {
            var o = {
                lang: self.lang,
                langs: self.screen.langs,
                module_id: self.screen.config.module_id,
                items: self.original['enum'],
                property_name: self.field,
                multimedia: self.screen.config.multimedia,
                values_are_icons: self.original.format === 'enum-image',
                keys_are_conditions: self.original.format === 'conditional-enum',
            };
            self.enum_extra = uiElement.key_value_mapping(o);
        }());
        var graphConfigurationUiElement = hqImport('app_manager/js/details/graph_config').graphConfigurationUiElement;
        self.graph_extra = graphConfigurationUiElement({
            childCaseTypes: self.screen.childCaseTypes,
            fixtures: self.screen.fixtures,
            lang: self.lang,
            langs: self.screen.langs,
            name: self.header.val(),
        }, self.original.graph_configuration);
        self.header.on("change", function () {
            // The graph should always have the same name as the columnModel
            self.graph_extra.setName(self.header.val());
        });

        var yyyy = new Date().getFullYear(),
            yy = String(yyyy).substring(2);
        self.date_extra = uiElement.select([{
            label: '31/10/' + yy,
            value: '%d/%m/%y',
        }, {
            label: '31/10/' + yyyy,
            value: '%d/%m/%Y',
        }, {
            label: '10/31/' + yyyy,
            value: '%m/%d/%Y',
        }, {
            label: '10/31/' + yy,
            value: '%m/%d/%y',
        }, {
            label: gettext('Oct 31, ') + yyyy,
            value: '%b %d, %Y',
        }]).val(self.original.date_format);
        self.date_extra.ui.prepend($('<div/>').text(gettext(' Format ')));

        self.late_flag_extra = uiElement.input().val(self.original.late_flag.toString());
        self.late_flag_extra.ui.find('input').css('width', 'auto').css("display", "inline-block");
        self.late_flag_extra.ui.prepend($('<span>' + gettext(' Days late ') + '</span>'));

        self.filter_xpath_extra = uiElement.input().val(self.original.filter_xpath.toString());
        self.filter_xpath_extra.ui.prepend($('<div/>'));

        self.calc_xpath_extra = uiElement.input().val(self.original.calc_xpath.toString());
        self.calc_xpath_extra.ui.prepend($('<div/>'));

        self.time_ago_extra = uiElement.select([{
            label: gettext('Years since date'),
            value: Utils.TIME_AGO.year,
        }, {
            label: gettext('Months since date'),
            value: Utils.TIME_AGO.month,
        }, {
            label: gettext('Weeks since date'),
            value: Utils.TIME_AGO.week,
        }, {
            label: gettext('Days since date'),
            value: Utils.TIME_AGO.day,
        }, {
            label: gettext('Days until date'),
            value: -Utils.TIME_AGO.day,
        }, {
            label: gettext('Weeks until date'),
            value: -Utils.TIME_AGO.week,
        }, {
            label: gettext('Months until date'),
            value: -Utils.TIME_AGO.month,
        }]).val(self.original.time_ago_interval.toString());
        self.time_ago_extra.ui.prepend($('<div/>').text(gettext(' Measuring ')));

        function fireChange() {
            self.fire('change');
        }
        _.each([
            'model',
            'field',
            'header',
            'nodeset_extra',
            'relevant',
            'format',
            'date_extra',
            'enum_extra',
            'graph_extra',
            'late_flag_extra',
            'filter_xpath_extra',
            'calc_xpath_extra',
            'time_ago_extra',
        ], function (element) {
            self[element].on('change', fireChange);
        });
        self.case_tile_field.subscribe(fireChange);

        self.$format = $('<div/>').append(self.format.ui);
        self.$format.find("select").css("margin-bottom", "5px");
        self.format.on('change', function () {
            // Prevent self from running on page load before init
            if (self.format.ui.parent().length > 0) {
                self.date_extra.ui.detach();
                self.enum_extra.ui.detach();
                self.graph_extra.ui.detach();
                self.late_flag_extra.ui.detach();
                self.filter_xpath_extra.ui.detach();
                self.calc_xpath_extra.ui.detach();
                self.time_ago_extra.ui.detach();
                if (this.val() === "date") {
                    self.format.ui.parent().append(self.date_extra.ui);
                    var format = self.date_extra.ui.find('select');
                    format.change(function () {
                        self.date_extra.value = format.val();
                        fireChange();
                    });
                    self.date_extra.value = format.val();
                } else if (this.val() === "enum" || this.val() === "enum-image" || this.val() === 'conditional-enum') {
                    self.enum_extra.values_are_icons(this.val() === 'enum-image');
                    self.enum_extra.keys_are_conditions(this.val() === 'conditional-enum');
                    self.format.ui.parent().append(self.enum_extra.ui);
                } else if (this.val() === "graph") {
                    // Replace format select with edit button
                    var parent = self.format.ui.parent();
                    parent.empty();
                    parent.append(self.graph_extra.ui);
                } else if (this.val() === 'late-flag') {
                    self.format.ui.parent().append(self.late_flag_extra.ui);
                    var input = self.late_flag_extra.ui.find('input');
                    input.change(function () {
                        self.late_flag_extra.value = input.val();
                        fireChange();
                    });
                } else if (this.val() === 'filter') {
                    self.format.ui.parent().append(self.filter_xpath_extra.ui);
                    var filter = self.filter_xpath_extra.ui.find('input');
                    filter.change(function () {
                        self.filter_xpath_extra.value = filter.val();
                        fireChange();
                    });
                } else if (this.val() === 'time-ago') {
                    self.format.ui.parent().append(self.time_ago_extra.ui);
                    var interval = self.time_ago_extra.ui.find('select');
                    interval.change(function () {
                        self.time_ago_extra.value = interval.val();
                        fireChange();
                    });
                }
            }
        }).fire('change');
        // Note self bind to the $edit_view for self google analytics event
        // (as opposed to the format object itself)
        // because self way the events are not fired during the initialization
        // of the page.
        self.format.$edit_view.on("change", function (event) {
            hqImport('analytix/js/google').track.event('Case List Config', 'Display Format', event.target.value);
        });
        self.serialize = function () {
            var column = self.original;
            column.field = self.field.val();
            column.header[self.lang] = self.header.val();
            //column.nodeset = self.nodeset.val();    // TODO: support saving new properties
            column.relevant = self.relevant.val();  // TODO: this can move into the self.isTab block below, no?
            column.format = self.format.val();
            column.date_format = self.date_extra.val();
            column.enum = self.enum_extra.getItems();
            column.graph_configuration =
                self.format.val() === "graph" ? self.graph_extra.val() : null;
            column.late_flag = parseInt(self.late_flag_extra.val(), 10);
            column.time_ago_interval = parseFloat(self.time_ago_extra.val());
            column.filter_xpath = self.filter_xpath_extra.val();
            column.calc_xpath = self.calc_xpath_extra.val();
            column.case_tile_field = self.case_tile_field();
            if (self.isTab) {
                // Note: starting_index is added by screenModel.serialize
                // TODO: support saving new properties
                /*return _.extend({
                    starting_index: self.starting_index,
                    has_nodeset: column.hasNodeset,
                }, _.pick(column, ['header', 'isTab', 'nodeset', 'relevant']));*/
            }
            return column;
        };
        self.setGrip = function (grip) {
            self.grip = grip;
        };
        self.copyCallback = function () {
            var column = self.serialize();
            // add a marker self self is copied for self purpose
            return JSON.stringify({
                type: 'detail-screen-config:Column',
                contents: column,
            });
        };

        return self;
    };
});
