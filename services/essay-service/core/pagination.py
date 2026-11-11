from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        return Response({
            "count": self.page.paginator.count,
            "total_pages": self.page.paginator.num_pages,
            "current_page": self.page.number,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": data,
        })


class SubmissionsListPagination(StandardResultsPagination):
    """Phase 6, Task 6.1's own explicit "30/page" requirement for the
    admin Submissions Module's list — a smaller default than
    StandardResultsPagination's 50, since each row here carries more
    per-row context (student, batch, paper, score) than the simpler admin
    lists elsewhere in this service. Still overridable via
    ?page_size=... up to the inherited max_page_size, same as every other
    list in this service."""
    page_size = 30
