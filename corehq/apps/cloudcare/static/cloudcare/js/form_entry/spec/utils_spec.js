hqDefine("cloudcare/js/form_entry/spec/utils_spec", [
    "hqwebapp/js/initial_page_data",
    "cloudcare/js/form_entry/spec/fixtures",
    "cloudcare/js/form_entry/form_ui",
    "cloudcare/js/form_entry/utils",
], function (
    initialPageData,
    fixtures,
    formUI,
    utils,
) {
    describe('Formplayer utils', function () {
        it('Should determine if two answers are equal', function () {
            var answersEqual = utils.answersEqual,
                result;

            result = answersEqual('ben', 'bob');
            assert.isFalse(result);

            result = answersEqual('ben', 'ben');
            assert.isTrue(result);

            result = answersEqual(['b', 'e', 'n'], ['b', 'o', 'b']);
            assert.isFalse(result);

            result = answersEqual(['b', 'e', 'n'], ['b', 'e', 'n']);
            assert.isTrue(result);
        });

        it('Should get root form for questions', function () {
            /**
             *  Form's question tree:
             *      grouped-element-tile-row
             *          text
             *      grouped-element-tile-row
             *          group
             *              grouped-element-tile-row
             *                  textInGroup
             *      grouped-element-tile-row
             *          repeat group
             *              grouped-element-tile-row
             *                  textInRepeat
             */
            initialPageData.register("toggles_dict", { WEB_APPS_ANCHORED_SUBMIT: false });
            var text = fixtures.textJSON({ix: "0"}),
                textInGroup = fixtures.textJSON({ix: "1,0"}),
                group = fixtures.groupJSON({ix: "1", children: [textInGroup]}),
                textInRepeatGroup = fixtures.textJSON({ix: "2,0"}),
                repeatGroup = fixtures.groupJSON({ix: "2", children: [textInRepeatGroup], repeatable: "true"}),
                form = formUI.Form({
                    tree: [text, group, repeatGroup],
                });

            [text, group, repeatGroup] = form.children().map(child => child.children()[0]);
            [textInGroup] = group.children()[0].children();
            [textInRepeatGroup] = repeatGroup.children()[0].children();
            assert.equal(utils.getRootForm(text), form);
            assert.equal(utils.getRootForm(group), form);
            assert.equal(utils.getRootForm(textInGroup), form);

            assert.equal(utils.getBroadcastContainer(text), form);
            assert.equal(utils.getBroadcastContainer(textInGroup), form);
            assert.equal(utils.getBroadcastContainer(textInRepeatGroup), repeatGroup);

            initialPageData.unregister("toggles_dict");
        });
    });
});
