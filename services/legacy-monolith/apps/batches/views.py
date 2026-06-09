from django.db.models import Count
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404

from core.permissions import IsAdminUser
from core.responses import success_response, error_response
from .models import Batch
from .serializers import BatchSerializer


class BatchListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        batches = Batch.objects.annotate(student_count=Count("students")).order_by("-created_at")
        serializer = BatchSerializer(batches, many=True)
        return success_response(data=serializer.data)

    def post(self, request):
        serializer = BatchSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        batch = serializer.save()
        result = BatchSerializer(Batch.objects.annotate(student_count=Count("students")).get(pk=batch.pk))
        return success_response(data=result.data, message="Batch created successfully", status_code=201)


class BatchDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get_batch(self, pk):
        return get_object_or_404(Batch.objects.annotate(student_count=Count("students")), pk=pk)

    def get(self, request, pk):
        batch = self._get_batch(pk)
        return success_response(data=BatchSerializer(batch).data)

    def put(self, request, pk):
        batch = self._get_batch(pk)
        serializer = BatchSerializer(batch, data=request.data, partial=False)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        updated = Batch.objects.annotate(student_count=Count("students")).get(pk=pk)
        return success_response(data=BatchSerializer(updated).data, message="Batch updated successfully")

    def patch(self, request, pk):
        batch = self._get_batch(pk)
        serializer = BatchSerializer(batch, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        updated = Batch.objects.annotate(student_count=Count("students")).get(pk=pk)
        return success_response(data=BatchSerializer(updated).data, message="Batch updated successfully")

    def delete(self, request, pk):
        batch = self._get_batch(pk)
        if batch.students.exists():
            return error_response(
                message="Cannot delete batch with existing students",
                status_code=400,
            )
        batch.delete()
        return success_response(message="Batch deleted successfully")
