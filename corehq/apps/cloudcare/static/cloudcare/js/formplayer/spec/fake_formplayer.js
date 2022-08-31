/**
 * Generates mock formplayer responses. Use as a fake for queryFormplayer.
 *
 * This does not support many of the options that can be passed to the real queryFormplayer.
 * It primarily fakes the selections logic.
 *
 * This contains one app, which has the following structure:
 *      m0: a menu that does not use cases
 *          m0-f0
 *      m1: a menu that uses cases
 *          m1-f0: a form that updates a case
 *  No menus use display-only forms.
 */
hqDefine("cloudcare/js/formplayer/spec/fake_formplayer", function () {
    var AssertProperties = hqImport("hqwebapp/js/assert_properties"),
        module = {},
        apps = {
            'abc123': {
                title: "My App",
                commands: [
                    {
                        title: "Survey Menu",
                        commands: [{
                            title: "Survey Form",
                        }],
                    },
                    {
                        title: "Some Cases",
                        commands: [{
                            title: "Followup Form",
                        }],
                        entities: [{
                            id: 'some_case_id',
                            name: 'Some Case',
                        }],
                        actions: [{
                            title: "Search for Case",
                            queryKey: "search_command.m1",
                            displays: [{
                                id: "dob",
                            }],
                        }],
                    },
                ],
            },
        };

    var navigateMenuStart = function (app) {
        return module.makeCommandResponse({
            title: app.title,
            breadcrumbs: [app.title],
            commands: app.commands,
        });
    };

    var navigateMenu = function (app, options) {
        var currentMenu = app,
            selections = options.selections,
            breadcrumbs = [app.title],
            needEntity = false,
            action = undefined;

        if (!selections || !selections.length) {
            throw new Error("No selections given to navigate_menu");
        }

        _.each(selections, function (selection) {
            var item = currentMenu.commands[selection];     // is selection a command?
            if (item) {
                currentMenu = currentMenu.commands[selection];
                needEntity = !!currentMenu.entities;
                breadcrumbs.push(currentMenu.title);
            }
            if (!item) {
                item = _.findWhere(currentMenu.entities, {id: selection});  // is selection a case id?
                if (item) {
                    needEntity = false;
                    breadcrumbs.push(item.name);
                }
            }
            if (selection.startsWith("action ")) {   // actions are assumed to be case search
                item = currentMenu.actions[selection.replace("action ", "")];
                if (item) {
                    var menuQueryData = options.queryData ? options.queryData[sessionStorage.queryKey] : undefined;
                    if (menuQueryData && menuQueryData.inputs) {
                        // run search and show results
                        needEntity = true;
                    } else {
                        // show search screen
                        action = item;
                        needEntity = false;
                    }
                }
            }
            if (!item) {
                throw new Error("Could not select " + selection);
            }
        });

        var responseOptions = {
            title: currentMenu.title,
            breadcrumbs: breadcrumbs,
        };
        if (needEntity) {
            return module.makeEntityResponse(_.extend(responseOptions, {
                entities: currentMenu.entities,
            }));
        } else if (action) {
            return module.makeQueryResponse(_.extend(responseOptions, {
                displays: action.displays,
                queryKey: action.queryKey,
            }));
        }
        return module.makeCommandResponse(_.extend(responseOptions, {
            commands: currentMenu.commands,
        }));
    };

    module.queryFormplayer = function (options, route) {
        var app = apps[options.appId];
        if (!app) {
            throw new Error("Could not find app " + options.appId);
        }

        switch (route) {
            case "navigate_menu_start":
                return navigateMenuStart(app);
            case "navigate_menu":
                return navigateMenu(app, options);
            default:
                throw new Error("Did not recognize route " + route);
        }
        return {success: 1};
    };

    var makeResponse = function (options) {
        AssertProperties.assertRequired(["title", "breadcrumbs"]);
        return _.defaults(options, {
            "notification": {"message": null, "error": false},
            "clearSession": false,
            "appId": "5319fe096062b0e282bf37e6faa81566",
            "appVersion": "CommCare Version: 2.27, App Version: 93",
            "locales": ["default", "en", "hin"],
            "menuSessionId": "e9fad761-5239-4096-bb71-0aba1ebd7377",
        });
    };

    module.makeCommandResponse = function (options) {
        AssertProperties.assertRequired(["commands"]);
        return _.defaults(makeResponse(options), {
            type: "commands",
        });
    };

    module.makeEntityResponse = function (options) {
        AssertProperties.assertRequired(["entities"]);
        return _.defaults(makeResponse(options), {
            "numEntitiesPerRow": 0,
            "pageCount": 2,
            "currentPage": 0,
            "type": "entities",
            "usesCaseTiles": false,
            "maxWidth": 0,
            "maxHeight": 0,
        });
    };

    module.makeQueryResponse = function (options) {
        AssertProperties.assertRequired(["displays", "queryKey"]);
        return _.defaults(makeResponse(options), {
            type: "query",
        });
    };

    return module;
});
