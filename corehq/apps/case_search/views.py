import json
import re

from django.http import Http404

from django.urls import reverse
from django.utils.translation import ugettext_lazy
from dimagi.utils.web import json_response

from corehq.apps.case_search.models import case_search_enabled_for_domain
from corehq.apps.domain.decorators import cls_require_superuser_or_contractor
from corehq.apps.domain.views.base import BaseDomainView
from corehq.util.view_utils import BadRequest, json_error


class CaseSearchView(BaseDomainView):
    section_name = ugettext_lazy("Data")
    template_name = 'case_search/case_search.html'
    urlname = 'case_search'
    page_title = ugettext_lazy("Case Search")

    @property
    def section_url(self):
        return reverse("data_interfaces_default", args=[self.domain])

    @property
    def page_url(self):
        return reverse(self.urlname, args=[self.domain])

    @property
    def page_context(self):
        context = super().page_context
        context.update({
            'settings_url': reverse("case_search_config", args=[self.domain]),
        })
        return context

    @cls_require_superuser_or_contractor
    def get(self, request, *args, **kwargs):
        if not case_search_enabled_for_domain(self.domain):
            raise Http404("Domain does not have case search enabled")

        return self.render_to_response(self.get_context_data())

    @json_error
    @cls_require_superuser_or_contractor
    def post(self, request, *args, **kwargs):
        from corehq.apps.es.case_search import CaseSearchES
        if not case_search_enabled_for_domain(self.domain):
            raise BadRequest("Domain does not have case search enabled")

        query = json.loads(request.POST.get('q'))
        case_type = query.get('type')
        owner_id = query.get('owner_id')
        search_params = query.get('parameters', [])
        include_closed = query.get("includeClosed", False)
        xpath = query.get("xpath")
        search = CaseSearchES()
        search = search.domain(self.domain).size(10)
        if not include_closed:
            search = search.is_closed(False)
        if case_type:
            search = search.case_type(case_type)
        if owner_id:
            search = search.owner(owner_id)
        for param in search_params:
            value = re.sub(param.get('regex', ''), '', param.get('value'))
            search = search.case_property_query(
                param.get('key'),
                value,
                clause=param.get('clause'),
                fuzzy=param.get('fuzzy'),
            )

        if xpath:
            search = search.xpath_query(self.domain, xpath)
        search_results = search.run()
        return json_response({
            'values': search_results.raw_hits,
            'count': search_results.total,
            'took': search_results.raw['took'],
            'query': search_results.query.dumps(pretty=True),
        })
