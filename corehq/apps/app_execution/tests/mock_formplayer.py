import dataclasses
import json
from functools import cached_property

from corehq.apps.app_execution.api import BaseFormplayerClient
from corehq.apps.app_execution.tests import response_factory as factory


@dataclasses.dataclass
class Screen:
    name: str
    children: list

    def process_selections(self, selections):
        option = self
        for selection in selections:
            option = option.get_next(selection)
        return option

    def get_next(self, selection):
        return self.children[int(selection)]

    def get_response_data(self, selections):
        pass


@dataclasses.dataclass
class Menu(Screen):
    def get_response_data(self, selections):
        return factory.command_response(selections, [child.name for child in self.children])


@dataclasses.dataclass
class CaseList(Screen):
    cases: list = dataclasses.field(default_factory=list)

    @cached_property
    def entities(self):
        return factory.make_entities(self.cases)

    def get_response_data(self, selections):
        return factory.entity_list_response(selections, self.entities)

    def get_next(self, selection):
        assert selection in [e["id"] for e in self.entities], selection
        return Menu(name="Forms", children=self.children)


@dataclasses.dataclass
class Form(Screen):

    def get_response_data(self, selections):
        return factory.form_response(selections, self.children)


class MockFormplayerClient(BaseFormplayerClient):
    def __init__(self, app):
        self.app = app
        self.form_session = {}
        super().__init__("domain", "username", "user_id")

    def _make_request(self, endpoint, data_bytes, headers):
        data = json.loads(data_bytes.decode("utf-8"))
        if "navigate_menu" in endpoint:
            selections = data["selections"]
            option = self.app.process_selections(selections)
            data = option.get_response_data(selections)
            if isinstance(option, Form):
                self.form_session = data
            return data
        else:
            # form response
            if not self.form_session:
                raise ValueError("No session data")
            assert data.get("session_id") == self.form_session["session_id"]
            if data["action"] == "answer":
                self.form_session["tree"][int(data["ix"])]["answer"] = data["answer"]
            elif data["action"] == "submit-all":
                return {"submitResponseMessage": "success", "nextScreen": None}
            return self.form_session
